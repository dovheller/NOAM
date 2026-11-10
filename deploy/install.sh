#!/bin/bash
# התקנת NOAM על Ubuntu 24.04 שהותקן מ-deploy/autoinstall. מריצים פעם אחת, מתוך עותק של הריפו, כ-root.
# דורש אינטרנט בזמן ההתקנה בלבד (pip). אחרי ההתקנה העמדה מנותקת (nftables).
# לא אומת על חומרה.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }

echo "== משתמשים וקבוצות"
getent group noam >/dev/null || groupadd --system noam
id noam-svc >/dev/null 2>&1 || useradd --system --gid noam --groups plugdev --home /var/lib/noam --shell /usr/sbin/nologin noam-svc
id noam-kiosk >/dev/null 2>&1 || useradd --create-home --groups video,render,input --shell /usr/sbin/nologin noam-kiosk

echo "== תיקיות (700: רק השירות)"
install -d -o noam-svc -g noam -m 0700 /var/lib/noam /var/lib/noam/audit /var/lib/noam/reports /var/lib/noam/keys
install -d -o root -g noam -m 0750 /etc/noam
install -d -m 0755 /media/noam /media/noam-src
install -d -o noam-svc -g noam -m 0770 /media/noam/NOAM-SSD

echo "== תוכנה"
python3 -m venv /opt/noam/venv
/opt/noam/venv/bin/pip install --upgrade pip
/opt/noam/venv/bin/pip install "$REPO"
install -m 0755 "$REPO/deploy/bin/noam-mark-target" /usr/local/bin/noam-mark-target

echo "== הגדרות"
[ -f /etc/noam/config.toml ] || install -o root -g noam -m 0640 "$REPO/config.example.toml" /etc/noam/config.toml
if [ ! -f /etc/noam/secrets.env ]; then
  umask 077
  echo "NOAM_AUDIT_KEY=$(head -c 32 /dev/urandom | base64 | tr -d '=+/')" > /etc/noam/secrets.env
  chown root:noam /etc/noam/secrets.env; chmod 0640 /etc/noam/secrets.env
fi
install -m 0644 "$REPO/deploy/nftables.conf" /etc/noam/nftables.conf

echo "== דיסק היעד (fstab לפי תווית)"
grep -q "LABEL=NOAM-SSD" /etc/fstab || \
  echo "LABEL=NOAM-SSD /media/noam/NOAM-SSD exfat defaults,nofail,uid=$(id -u noam-svc),gid=$(getent group noam | cut -d: -f3),umask=007,x-systemd.device-timeout=5 0 0" >> /etc/fstab

echo "== udev"
install -m 0644 "$REPO"/deploy/udev/*.rules /etc/udev/rules.d/
udevadm control --reload

echo "== systemd"
install -m 0644 "$REPO"/deploy/systemd/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable noam-firewall.service noam-station.service noam-kiosk.service
systemctl set-default graphical.target

cat <<'MSG'

== נשאר לעשות ידנית (פעם אחת):
1. ערוך /etc/noam/config.toml — שם, כתובת, טלפון, קוד הגדרות (operator.pin).
2. צור את מפתח החתימה (דב ונועם יחד, כל אחד שומר את הסיסמה במנהל הסיסמאות שלו):
     sudo -u noam-svc /opt/noam/venv/bin/python -c "from noam.report import generate_key; import getpass; \
       print(generate_key('/var/lib/noam/keys/station.pem', getpass.getpass('סיסמת מנהל (12+ תווים): '), 'נועם הלר'))"
   ושמור עותק של station.pub.pem ו-station.crt מחוץ לעמדה (לאימות דוחות).
3. חבר את דיסק היעד (תווית NOAM-SSD), ואז:  sudo noam-mark-target /media/noam/NOAM-SSD
4. הגדר כתובת קבועה 10.77.0.1/24 לכרטיס הרשת שמחובר לראוטר הסגור (netplan).
5. אתחל:  sudo reboot
MSG
