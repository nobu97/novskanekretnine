def generate_common_table(ads, title):
    if not ads:
        return f"<h3>{title}</h3><p><strong>Nema oglasa za danas.</strong></p><br>"

    html = f"<h3>{title}</h3>"
    html += "<table border='1' cellpadding='5' cellspacing='0'>"
    html += (
        "<tr><th>Naziv</th><th>Tip objekta</th><th>Lokacija</th><th>Cijena</th><th>Cijena/m2</th>"
        "<th>Broj soba</th><th>Godina izgradnje</th><th>Površina</th><th>Objavljeno</th><th>Opis</th><th>Izvor</th><th>Link</th></tr>"
    )
    for ad in ads:
        html += f"<tr>"
        html += f"<td>{ad.get('title', 'N/A')}</td>"
        html += f"<td>{ad.get('type', 'N/A')}</td>"
        html += f"<td>{ad.get('location', 'N/A')}</td>"
        html += f"<td>{ad.get('price', 'N/A')}</td>"
        html += f"<td>{ad.get('price_per_m2', 'N/A')}</td>"
        html += f"<td>{ad.get('number_of_rooms', 'N/A')}</td>"
        html += f"<td>{ad.get('year_built', 'N/A')}</td>"
        html += f"<td>{ad.get('area', 'N/A')}</td>"
        html += f"<td>{ad.get('date_posted', 'N/A')}</td>"
        html += f"<td>{ad.get('description', 'N/A')}</td>"
        html += f"<td>{ad.get('source', 'N/A')}</td>"
        html += f"<td><a href='{ad.get('href', '#')}' target='_blank'>Otvori</a></td>"
        html += f"</tr>"
    html += "</table><br><br>"
    html += f"<p><strong>Ukupno pronađeno oglasa: {len(ads)}</strong></p><br>"
    return html
