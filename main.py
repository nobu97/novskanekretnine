import os
import csv
from pathlib import Path
import nest_asyncio

nest_asyncio.apply()

import asyncio
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import smtplib

from scrapers import extract_ads_index, scrape_plavi_oglasnik, extract_ads_gohome
from tables import generate_common_table


# -------------------- URL Predlošci -------------------- #

HOUSE_URL_TEMPLATE = (
    "https://www.index.hr/oglasi/nekretnine/prodaja-kuca/pretraga?"
    "searchQuery=%257B%2522category%2522%253A%2522prodaja-kuca%2522%252C"
    "%2522module%2522%253A%2522nekretnine%2522%252C%2522sortOption%2522%253A4%252C"
    "%2522priceTo%2522%253A%2522220000%2522%252C%2522numberOfRoomsFrom%2522%253A%25223%2522%252C"
    "%2522page%2522%253A{page}%257D"
)

FLAT_URL_TEMPLATE = (
    "https://www.index.hr/oglasi/nekretnine/prodaja-stanova/pretraga?"
    "searchQuery=%257B%2522category%2522%253A%2522prodaja-stanova%2522%252C%2522module%2522%253A%2522nekretnine%2522%252C"
    "%2522priceTo%2522%253A%2522220000%2522%252C%2522numberOfRoomsFrom%2522%253A%25223%2522%252C"
    "%2522page%2522%253A{page}%252C%2522sortOption%2522%253A4%257D"
)

PLAVI_KUCE_URL = "https://www.oglasnik.hr/kuce-prodaja?ad_price_from=50000&ad_price_to=220000"
PLAVI_STANOVI_URL = "https://www.oglasnik.hr/stanovi-prodaja?ad_price_from=50000&ad_price_to=220000"

GOHOME_KUCE_URL = (
    "https://www.gohome.hr/nekretnine.aspx?q=od+50000+do+200000+ku%e6a+%b9to+jeftinije+Oglasi+objavljeni+od+zadnjeg+puta&str={page_num}"
)
GOHOME_STANOVI_URL = (
    "https://www.gohome.hr/nekretnine.aspx?q=od+50000+do+220000+stan+%b9to+jeftinije+Oglasi+objavljeni+od+zadnjeg+puta&str={page_num}"
)

# -------------------- Filter: samo lokacije -------------------- #

TARGETS = ["novska", "jarun", "samobor"]


def _matches_targets(ad: dict) -> bool:
    hay = " ".join(
        [
            str(ad.get("location", "")),
            str(ad.get("title", "")),
            str(ad.get("description", "")),
        ]
    ).lower()
    return any(t in hay for t in TARGETS)


def filter_ads(ads: list[dict]) -> list[dict]:
    return [ad for ad in ads if _matches_targets(ad)]


# -------------------- CSV spremanje -------------------- #

def save_ads_csv(filename: str, blocks: list[tuple[str, str, list[dict]]]) -> str:
    """
    blocks: [(source, category, ads), ...]
    """
    out_dir = Path("output")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / filename

    fieldnames = [
        "source",
        "category",
        "title",
        "location",
        "price",
        "price_per_m2",
        "area",
        "number_of_rooms",
        "year_built",
        "date_posted",
        "description",
        "href",
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for source, category, ads in blocks:
            for ad in ads:
                row = {k: ad.get(k, "") for k in fieldnames}
                row["source"] = source
                row["category"] = category
                w.writerow(row)

    return str(out_path)


# -------------------- Email (HTML + attachment) -------------------- #

def send_email(subject, html_body, sender_email, app_password, recipient_emails, attachments=None):
    if not sender_email or not app_password or not recipient_emails:
        raise ValueError("Missing EMAIL_USERNAME / EMAIL_PASSWORD / EMAIL_RECIPIENTS env vars.")

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = ", ".join(recipient_emails)

    msg.attach(MIMEText(html_body, "html"))

    attachments = attachments or []
    for path in attachments:
        with open(path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        filename = os.path.basename(path)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, app_password)
        server.sendmail(sender_email, recipient_emails, msg.as_string())


# -------------------- Glavna rutina -------------------- #

async def main():
    index_houses, index_flats, plavi_houses, plavi_flats, gohome_kuce, gohome_stanovi = await asyncio.gather(
        extract_ads_index(HOUSE_URL_TEMPLATE),
        extract_ads_index(FLAT_URL_TEMPLATE),
        scrape_plavi_oglasnik(PLAVI_KUCE_URL),
        scrape_plavi_oglasnik(PLAVI_STANOVI_URL),
        extract_ads_gohome(GOHOME_KUCE_URL),
        extract_ads_gohome(GOHOME_STANOVI_URL),
    )

    # Filter (Novska / Jarun / Samobor)
    index_houses = filter_ads(index_houses)
    index_flats = filter_ads(index_flats)
    plavi_houses = filter_ads(plavi_houses)
    plavi_flats = filter_ads(plavi_flats)
    gohome_kuce = filter_ads(gohome_kuce)
    gohome_stanovi = filter_ads(gohome_stanovi)

    # HTML mail
    html = f"<h2>Filtrirano: {', '.join([t.title() for t in TARGETS])}</h2>"

    html += "<h2>Kuće</h2>"
    html += generate_common_table(index_houses, "Index oglasi")
    html += generate_common_table(plavi_houses, "Plavi oglasnik")
    html += generate_common_table(gohome_kuce, "GoHome oglasnik")

    html += "<h2>Stanovi</h2>"
    html += generate_common_table(index_flats, "Index oglasi")
    html += generate_common_table(plavi_flats, "Plavi oglasnik")
    html += generate_common_table(gohome_stanovi, "GoHome oglasnik")

    # CSV attachment
    today_iso = datetime.now().strftime("%Y-%m-%d")
    csv_path = save_ads_csv(
        f"nekretnine_{today_iso}_novska_jarun_samobor.csv",
        [
            ("Index", "Kuće", index_houses),
            ("Index", "Stanovi", index_flats),
            ("Plavi", "Kuće", plavi_houses),
            ("Plavi", "Stanovi", plavi_flats),
            ("GoHome", "Kuće", gohome_kuce),
            ("GoHome", "Stanovi", gohome_stanovi),
        ],
    )

    # ENV (secrets)
    sender = os.getenv("EMAIL_USERNAME")
    password = os.getenv("EMAIL_PASSWORD")
    recipients = [e.strip() for e in os.getenv("EMAIL_RECIPIENTS", "").split(",") if e.strip()]

    today_hr = datetime.now().strftime("%d.%m.%Y.")
    send_email(
        subject=f"Nekretnine (Novska/Jarun/Samobor) {today_hr}",
        html_body=html,
        sender_email=sender,
        app_password=password,
        recipient_emails=recipients,
        attachments=[csv_path],
    )


if __name__ == "__main__":
    asyncio.run(main())