from datetime import datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PwTimeout


DEFAULT_NAV_TIMEOUT_MS = 90_000
DEFAULT_GOTO_TRIES = 3


async def _goto_with_retry(page, url: str, timeout_ms: int = DEFAULT_NAV_TIMEOUT_MS, tries: int = DEFAULT_GOTO_TRIES) -> bool:
    last_exc = None
    for i in range(tries):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return True
        except PwTimeout as e:
            last_exc = e
            await page.wait_for_timeout(1500 * (i + 1))
        except Exception as e:
            last_exc = e
            await page.wait_for_timeout(800 * (i + 1))

    print(f"GOTO FAILED: url={url} err={type(last_exc).__name__ if last_exc else 'unknown'}")
    return False


async def extract_ads_index(url_template):
    today_short = datetime.now().strftime("%d.%m.%y")
    today_full = datetime.now().strftime("%d.%m.%Y.")
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        list_page = await browser.new_page()
        list_page.set_default_timeout(DEFAULT_NAV_TIMEOUT_MS)
        list_page.set_default_navigation_timeout(DEFAULT_NAV_TIMEOUT_MS)

        page_num = 1

        while True:
            search_url = url_template.format(page=page_num)
            ok = await _goto_with_retry(list_page, search_url)
            if not ok:
                break

            await list_page.wait_for_timeout(2000)
            html = await list_page.content()
            soup = BeautifulSoup(html, "html.parser")

            daily_ads_found = 0

            for a in soup.find_all("a", class_="AdLink__link___3Iz86"):
                info_div = a.find("div", class_="AdSummary__info___2tUOv")
                if not info_div:
                    continue
                date_span = info_div.find("span")
                if not date_span or date_span.get_text(strip=True) != today_full:
                    continue

                daily_ads_found += 1
                title = a.get("title", "").strip()
                href = f"https://www.index.hr{a.get('href', '')}"

                detail_page = await browser.new_page()
                detail_page.set_default_timeout(DEFAULT_NAV_TIMEOUT_MS)
                detail_page.set_default_navigation_timeout(DEFAULT_NAV_TIMEOUT_MS)

                ok_detail = await _goto_with_retry(detail_page, href)
                if not ok_detail:
                    await detail_page.close()
                    continue

                await detail_page.wait_for_timeout(1500)
                ad_soup = BeautifulSoup(await detail_page.content(), "html.parser")

                published_span = ad_soup.find("span", string=lambda s: s and "Objavljen:" in s)
                if not published_span:
                    await detail_page.close()
                    continue

                published_date_str = (
                    published_span.get_text(strip=True)
                    .split("Objavljen:")[1]
                    .strip()
                    .split(" ")[0]
                    .strip(".")
                )
                if published_date_str != today_short:
                    await detail_page.close()
                    continue

                price_span = ad_soup.find("span", class_="SummarySection__price___1dmYQ")
                total_price = price_span.get_text(strip=True) if price_span else "N/A"
                price_m2_span = ad_soup.find("span", class_="SummarySection__priceM2___1L68A")
                price_per_m2 = price_m2_span.get_text(" ", strip=True) if price_m2_span else "N/A"

                location = "N/A"
                location_label = ad_soup.find("div", string=lambda s: s and "Lokacija" in s)
                if location_label:
                    location_div = location_label.find_next_sibling("div")
                    location = location_div.get_text(separator=" ", strip=True) if location_div else "N/A"

                number_of_rooms = year_built = area = "N/A"
                info_blocks = ad_soup.find_all("div", class_="SpecialSection__specialCardContent___ISmYx")

                for block in info_blocks:
                    label_div = block.find("div", class_="SpecialSection__iconContainer___1iKeI")
                    value_div = block.find("div", class_="SpecialSection__value___383Fy")
                    if not label_div or not value_div:
                        continue
                    label_text = label_div.get_text(strip=True)
                    value_text = value_div.get_text(strip=True)
                    if label_text == "Broj soba":
                        number_of_rooms = value_text
                    elif label_text == "Godina izgradnje":
                        year_built = value_text
                    elif label_text == "Stambena površina":
                        area = value_text

                results.append({
                    "title": title,
                    "href": href,
                    "price": total_price,
                    "price_per_m2": price_per_m2,
                    "number_of_rooms": number_of_rooms,
                    "year_built": year_built,
                    "area": area,
                    "location": location,
                    "date_posted": published_span.get_text(strip=True),
                })

                await detail_page.close()

            if daily_ads_found == 0:
                break
            page_num += 1

        await browser.close()
    return results


async def scrape_plavi_oglasnik(url):
    today = datetime.now().strftime("%d.%m.%Y.")
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.set_default_timeout(DEFAULT_NAV_TIMEOUT_MS)
        page.set_default_navigation_timeout(DEFAULT_NAV_TIMEOUT_MS)

        ok = await _goto_with_retry(page, url)
        if not ok:
            await browser.close()
            return results

        await page.wait_for_timeout(2000)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        for ad_wrapper in soup.find_all("a", class_="classified-box"):
            ad = ad_wrapper.find("div", class_="pad-xs-only-lr")
            if not ad:
                continue

            title = ad.find("h3", class_="classified-title").get_text(strip=True) if ad.find("h3", class_="classified-title") else "N/A"
            href = ad_wrapper.get("href", "N/A")
            price = ad.find("div", class_="price-block").find("span", class_="main").get_text(strip=True) if ad.find("div", class_="price-block") else "N/A"
            date_posted = ad.find("span", class_="date").get_text(strip=True) if ad.find("span", class_="date") else "N/A"
            if date_posted != today:
                continue

            house_type = area = "N/A"
            desc_block = ad.find("div", class_="description")
            if desc_block:
                for s in desc_block.find_all("span", class_="classified-param"):
                    label = s.get_text(strip=True)
                    if "Vrsta" in label:
                        v = s.find("span", class_="classified-param-value")
                        house_type = v.get_text(strip=True) if v else "N/A"
                    elif "Površina" in label:
                        v = s.find("span", class_="classified-param-value")
                        area = v.get_text(strip=True) if v else "N/A"

            location = "N/A"
            image_div = ad_wrapper.find("div", class_="image-wrapper-bg")
            if image_div:
                location_span = image_div.find("span", class_="location")
                location = location_span.get_text(strip=True) if location_span else "N/A"

            results.append({
                "title": title,
                "type": house_type,
                "area": area,
                "price": price,
                "date_posted": date_posted,
                "href": href,
                "location": location,
            })

        await browser.close()
    return results


async def extract_ads_bijelo_jaje(base_url):
    today = datetime.now().strftime("%d.%m.%Y.")
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.set_default_timeout(DEFAULT_NAV_TIMEOUT_MS)
        page.set_default_navigation_timeout(DEFAULT_NAV_TIMEOUT_MS)

        page_num = 1
        stop = False
        while not stop:
            url = base_url.format(page=page_num)
            ok = await _goto_with_retry(page, url)
            if not ok:
                break

            await page.wait_for_timeout(1500)
            soup = BeautifulSoup(await page.content(), "html.parser")
            ad_cards = soup.find_all("div", class_="flex-1 flex-col")

            if not ad_cards:
                break

            for card in ad_cards:
                try:
                    title_tag = card.find("span", class_="text-base font-semibold mb-2").find("a")
                    title = title_tag.get_text(strip=True)
                    href = "https://bijelojaje.dnevnik.hr" + title_tag.get("href", "")

                    location = card.find("ul", class_="flex items-center text-brand-primary text-sm").get_text(strip=True)

                    surface = flat_type = "N/A"
                    attrs = card.find_all("li", class_="rounded bg-gray-200 py-0.5 px-1 mr-1 mb-1")
                    for attr in attrs:
                        txt = attr.get_text(strip=True)
                        if "Stambena površina" in txt:
                            surface = txt.split(":")[-1].strip()
                        elif "Tip stana" in txt or "Vrsta" in txt:
                            flat_type = txt.split(":")[-1].strip()

                    detail_page = await browser.new_page()
                    detail_page.set_default_timeout(DEFAULT_NAV_TIMEOUT_MS)
                    detail_page.set_default_navigation_timeout(DEFAULT_NAV_TIMEOUT_MS)

                    okd = await _goto_with_retry(detail_page, href)
                    if not okd:
                        await detail_page.close()
                        continue

                    await detail_page.wait_for_timeout(1200)
                    detail_soup = BeautifulSoup(await detail_page.content(), "html.parser")

                    date_label = detail_soup.find("span", string=lambda s: s and "Oglas" in s)
                    if not date_label:
                        await detail_page.close()
                        continue

                    is_published = "objavljen" in date_label.text.lower()
                    date_value = date_label.find_next_sibling("span").get_text(strip=True)

                    if not is_published or date_value != today:
                        await detail_page.close()
                        stop = True
                        break

                    year_built = number_of_rooms = "N/A"
                    rows = detail_soup.find_all("tr")
                    for row in rows:
                        th = row.find("th")
                        td = row.find("td")
                        if not th or not td:
                            continue
                        label = th.get_text(strip=True)
                        value = td.get_text(strip=True)
                        if label == "Godina izgradnje":
                            year_built = value
                        elif label == "Broj soba":
                            number_of_rooms = value

                    price_div = detail_soup.find("div", class_="text-3xl font-bold")
                    price = price_div.get_text(strip=True) if price_div else "N/A"

                    results.append({
                        "title": title,
                        "location": location,
                        "area": surface,
                        "type": flat_type,
                        "href": href,
                        "price": price,
                        "number_of_rooms": number_of_rooms,
                        "year_built": year_built,
                        "date_posted": date_value,
                    })

                    await detail_page.close()
                except Exception as e:
                    print("ERROR:", e)
                    continue

            page_num += 1

        await browser.close()
    return results


async def extract_ads_gohome(base_url_template: str, scroll_lazy: bool = True, with_details: bool = False):
    """
    Ekstrakcija GoHome oglasa koji su označeni <p itemprop="datePosted" class="indexed">Danas</p>.
    Paginacija se rukuje offsetom 'str='.
    """

    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        page.set_default_timeout(DEFAULT_NAV_TIMEOUT_MS)
        page.set_default_navigation_timeout(DEFAULT_NAV_TIMEOUT_MS)

        page_num = 1

        while True:
            url = base_url_template.format(page_num=page_num)
            ok = await _goto_with_retry(page, url)
            if not ok:
                break

            if scroll_lazy:
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(2000)
                except Exception:
                    pass

            await page.wait_for_timeout(2000)
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            daily_ads = 0
            oglas_candidates = soup.find_all("div", class_=lambda v: v and "JQSearchResult" in v)

            for div in oglas_candidates:
                date_tag = div.find("p", class_="indexed", itemprop="datePosted")
                if not date_tag:
                    continue

                dt_text = date_tag.get_text(strip=True).strip(",").lower()
                if dt_text != "danas":
                    continue

                daily_ads += 1

                a = div.find("a", class_="JQEstateUrl")
                title = ""
                href = ""
                if a:
                    span_title = a.find("span", itemprop="name")
                    title = span_title.get_text(strip=True) if span_title else ""
                    href_rel = a.get("href", "").strip()
                    href = "https://www.gohome.hr" + href_rel

                price_meta = div.find("meta", itemprop="price")
                price = price_meta["content"] if price_meta else "N/A"
                currency_meta = div.find("meta", itemprop="priceCurrency")
                currency = currency_meta["content"] if currency_meta else ""
                price_str = f"{price} {currency}".strip()

                sqm_tag = div.find("span", class_="square-price")
                price_sqm = sqm_tag.get_text(strip=True) if sqm_tag else "N/A"

                desc_tag = div.find("p", class_="describe", itemprop="description")
                description = desc_tag.get_text(strip=True) if desc_tag else ""

                src_p = div.find("p", class_="source")
                src = src_p.get_text(strip=True) if src_p else "N/A"

                results.append({
                    "title": title,
                    "href": href,
                    "price": price_str,
                    "price_per_m2": price_sqm,
                    "date_posted": "Danas",
                    "description": description,
                    "source": src,
                })

            if daily_ads == 0:
                print("Nema vise oglasa 'Danas' -> prekid.")
                break

            page_num += 1

        await browser.close()

    return results