# Nekretnine scraper (Novska / Jarun / Samobor)

Script scrapa današnje oglase (Index, Plavi, GoHome), filtrira na Novska/Jarun/Samobor, šalje HTML mail i CSV prilog.

## Lokalno pokretanje

```bash
pip install -r requirements.txt
playwright install --with-deps chromium

export EMAIL_USERNAME="tvojmail@gmail.com"
export EMAIL_PASSWORD="tvoj_google_app_password"
export EMAIL_RECIPIENTS="tvojmail@gmail.com"

python main.py
