"""
Product Count Monitor
======================
Checks listing-page URLs, extracts the visible product count, and
appends the result to data/product_count_log.tsv and writes a per-URL
summary to data/product_count_summary.tsv.

Note - because of the FF Anbindung, a listing with 0 real results
falls back to showing the full catalog count instead of 0. As of
9.9.2026 only 9 URLs legitimately have a catalog above 150 products,
so anything above that threshold is treated as the fallback and
logged as 0, EXCEPT those 9 known exceptions (see
KNOWN_LARGE_CATALOG_URLS below). Both the corrected count
(product_count) and the real scraped number (raw_product_count) are
kept in the log, so a false positive is easy to spot and fix.
"""

import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup

# Log timestamps in German local time. ZoneInfo automatically applies
# CET (UTC+1) or CEST (UTC+2) depending on date - no manual DST math.
LOCAL_TZ = ZoneInfo("Europe/Berlin")

# ---- CONFIG: all listing pages here (edit as needed if there are changes) ----
URLS = [
    {"name": "Zyklon Staubsauger", "url": "https://www.medion.com/de/shop/zyklon-staubsauger"},
    {"name": "Work from Home PCs", "url": "https://www.medion.com/de/shop/work-from-home-pcs"},
    {"name": "work-from-home-alle", "url": "https://www.medion.com/de/shop/work-from-home-alle"},
    {"name": "Saugroboter Alexa", "url": "https://www.medion.com/de/shop/alexa-saugroboter"},
    {"name": "Saugroboter Alexa", "url": "https://www.medion.com/at/shop/alexa-saugroboter"},
    {"name": "Windows Update", "url": "https://www.medion.com/de/shop/windows-update"},
    {"name": "Versandkostenfrei", "url": "https://www.medion.com/de/shop/versandkostenfrei"},
    {"name": "Ventilatoren & Klimageräte", "url": "https://www.medion.com/de/shop/ventilatoren-klimageraete"},
    {"name": "Ventilatoren", "url": "https://www.medion.com/de/shop/ventilatoren"},
    {"name": "Vidaa TVs", "url": "https://www.medion.com/de/shop/tv/vidaa"},
    {"name": "TiVo TVs", "url": "https://www.medion.com/de/shop/tv/tivo"},
    {"name": "TV-Soundbars", "url": "https://www.medion.com/de/shop/tv/soundbars"},
    {"name": "Smart TV", "url": "https://www.medion.com/de/shop/tv/smart-tv"},
    {"name": "QLED TVs", "url": "https://www.medion.com/de/shop/tv/qled"},
    {"name": "Premium-TVs", "url": "https://www.medion.com/de/shop/tv/premium"},
    {"name": "OLED TVs", "url": "https://www.medion.com/de/shop/tv/oled"},
    {"name": "TVs mit Soundbar", "url": "https://www.medion.com/de/shop/tv/mit-soundbar"},
    {"name": "Mini LED Tvs", "url": "https://www.medion.com/de/shop/tv/mini-led"},
    {"name": "Mobilen TVs", "url": "https://www.medion.com/de/shop/tv/mini"},
    {"name": "TV Kaufberater Micro Dimming", "url": "https://www.medion.com/de/shop/tv/micro-dimming"},
    {"name": "TV HDR", "url": "https://www.medion.com/de/shop/tv/hdr"},
    {"name": "HD TVs", "url": "https://www.medion.com/de/shop/tv/hd"},
    {"name": "Fire TVs", "url": "https://www.medion.com/de/shop/tv/fire-tv"},
    {"name": "FHD TVs", "url": "https://www.medion.com/de/shop/tv/fhd"},
    {"name": "Einsteiger", "url": "https://www.medion.com/de/shop/tv/einsteiger"},
    {"name": "TV Dolby Vision", "url": "https://www.medion.com/de/shop/tv/dolby-vision"},
    {"name": "bis ca. 80 cm (32'')", "url": "https://www.medion.com/de/shop/tv/bis-32-zoll"},
    {"name": "Angebote TV", "url": "https://www.medion.com/de/shop/tv/angebote"},
    {"name": "Android TVs", "url": "https://www.medion.com/de/shop/tv/android-tv"},
    {"name": "ab ca. 139 cm (55in)", "url": "https://www.medion.com/de/shop/tv/ab-55-zoll"},
    {"name": "4K UHD TVs", "url": "https://www.medion.com/de/shop/tv/4k-uhd"},
    {"name": "ca. 98 cm - 126 cm (39in bis 50in)", "url": "https://www.medion.com/de/shop/tv/39-bis-50-zoll"},
    {"name": "Alle TVs", "url": "https://www.medion.com/de/shop/tv"},
    {"name": "Turmventilatoren", "url": "https://www.medion.com/de/shop/turmventilatoren"},
    {"name": "Topseller", "url": "https://www.medion.com/de/shop/topseller"},
    {"name": "Alle Tablets", "url": "https://www.medion.com/de/shop/tablets-alle"},
    {"name": "Staubsauger", "url": "https://www.medion.com/de/shop/staubsauger-alle"},
    {"name": "Sportliche Angebote", "url": "https://www.medion.com/de/shop/sportliche-angebote"},
    {"name": "Sommer Angebote", "url": "https://www.medion.com/de/shop/sommer-angebote"},
    {"name": "Smarte Produkte alle", "url": "https://www.medion.com/de/shop/smarte-produkte-alle"},
    {"name": "Poolroboter", "url": "https://www.medion.com/de/shop/haushalt/poolroboter"},
    {"name": "Alle Laptops", "url": "https://www.medion.com/de/shop/searchpages/alle-laptops"},
    {"name": "Poolroboter", "url": "https://www.medion.com/at/shop/haushalt/poolroboter"},
    {"name": "Saugroboter S-Serie", "url": "https://www.medion.com/at/shop/saugroboter-s-serie"},
    {"name": "Rückgaberecht", "url": "https://www.medion.com/de/shop/rueckgaberecht"},
    {"name": "PC-Zubehör", "url": "https://www.medion.com/de/shop/pc/zubehoer"},
    {"name": "Mäuse und Tastaturen", "url": "https://www.medion.com/de/shop/pc/tastatur-maus"},
    {"name": "Monitore", "url": "https://www.medion.com/de/shop/pc/monitor"},
    {"name": "Mini PCs", "url": "https://www.medion.com/de/shop/pc/mini"},
    {"name": "Drucker", "url": "https://www.medion.com/de/shop/pc/drucker"},
    {"name": "Desktop-PCs", "url": "https://www.medion.com/de/shop/pc/desktop"},
    {"name": "Angebote PC & Monitore", "url": "https://www.medion.com/de/shop/pc/angebote"},
    {"name": "All-in-One-PCs", "url": "https://www.medion.com/de/shop/pc/all-in-one"},
    {"name": "Alle PCs", "url": "https://www.medion.com/de/shop/pc/alle"},
    {"name": "Paypal null Prozent Finanzierung", "url": "https://www.medion.com/de/shop/paypal-null-prozent-finanzierung"},
    {"name": "Party", "url": "https://www.medion.com/de/shop/party"},
    {"name": "Nvidia 50er Serie Produkte", "url": "https://www.medion.com/de/shop/nvidia-rtx-serie-50"},
    {"name": "NVIDIA RTX Produkte", "url": "https://www.medion.com/de/shop/nvidia-rtx-produkte"},
    {"name": "NVIDIA RTX Laptops", "url": "https://www.medion.com/de/shop/nvidia-rtx-laptops"},
    {"name": "Nvidia rtx", "url": "https://www.medion.com/de/shop/nvidia-rtx"},
    {"name": "NVIDIA PC", "url": "https://www.medion.com/de/shop/nvidia-pc"},
    {"name": "Neuheiten", "url": "https://www.medion.com/de/shop/neuheiten"},
    {"name": "Multimedia-PC", "url": "https://www.medion.com/de/shop/multimedia-pc"},
    {"name": "Monitor-Angebote", "url": "https://www.medion.com/de/shop/monitore/angebote"},
    {"name": "Microsoft Jumpstart Gaming", "url": "https://www.medion.com/de/shop/microsoft-jumpstart-gaming"},
    {"name": "Microsoft Jumpstart", "url": "https://www.medion.com/de/shop/microsoft-jumpstart"},
    {"name": "Luftreiniger Alle", "url": "https://www.medion.com/de/shop/luftreiniger-alle"},
    {"name": "TV-Aktion", "url": "https://www.medion.com/de/shop/lp/tv-aktion"},
    {"name": "Laptop & PC Week", "url": "https://www.medion.com/de/shop/lp/laptop-pc-week"},
    {"name": "Intel Produkte", "url": "https://www.medion.com/de/shop/lp/intel-produkte"},
    {"name": "Intel PC", "url": "https://www.medion.com/de/shop/lp/intel-pc"},
    {"name": "Intel Games Bundle Produkte", "url": "https://www.medion.com/de/shop/lp/intel-games-bundle-produkte"},
    {"name": "Defender 17 P10", "url": "https://www.medion.com/de/shop/lp/erazer/defender-17-p10"},
    {"name": "Beast 16 X10", "url": "https://www.medion.com/de/shop/lp/erazer/beast-16-x10"},
    {"name": "Lieferung bis Weihnachten", "url": "https://www.medion.com/de/shop/lieferung-bis-weihnachten"},
    {"name": "Lenovo Produkte", "url": "https://www.medion.com/de/shop/lenovo-produkte"},
    {"name": "Laptop-Zubehör", "url": "https://www.medion.com/de/shop/laptops/zubehoer"},
    {"name": "Sprchrgd Laptops", "url": "https://www.medion.com/de/shop/laptops/sprchrgd"},
    {"name": "Multimedia-Laptops", "url": "https://www.medion.com/de/shop/laptops/multimedia"},
    {"name": "KI gestützte Laptops", "url": "https://www.medion.com/de/shop/laptops/ki"},
    {"name": "Intel Core i7", "url": "https://www.medion.com/de/shop/laptops/intel-core-i7"},
    {"name": "Intel Core i5", "url": "https://www.medion.com/de/shop/laptops/intel-core-i5"},
    {"name": "Intel Core Laptops", "url": "https://www.medion.com/de/shop/laptops/intel-core"},
    {"name": "Homeoffice Laptops", "url": "https://www.medion.com/de/shop/laptops/homeoffice"},
    {"name": "Einsteiger-Laptops", "url": "https://www.medion.com/de/shop/laptops/einsteiger"},
    {"name": "Laptops Angebote", "url": "https://www.medion.com/de/shop/laptops/angebote"},
    {"name": "AMD Ryzen", "url": "https://www.medion.com/de/shop/laptops/amd-ryzen"},
    {"name": "18'' Laptops", "url": "https://www.medion.com/de/shop/laptops/18-zoll"},
    {"name": "17'' Laptops", "url": "https://www.medion.com/de/shop/laptops/17-zoll"},
    {"name": "16'' Laptops", "url": "https://www.medion.com/de/shop/laptops/16-zoll"},
    {"name": "15'' Laptops", "url": "https://www.medion.com/de/shop/laptops/15-zoll"},
    {"name": "14'' Laptops", "url": "https://www.medion.com/de/shop/laptops/14-zoll"},
    {"name": "Alle Laptops", "url": "https://www.medion.com/de/shop/laptops"},
    {"name": "Reinigungsgeräte", "url": "https://www.medion.com/de/shop/kuechengeraete-reinigung"},
    {"name": "Frühstück", "url": "https://www.medion.com/de/shop/kuechengeraete-fruehstueck"},
    {"name": "Wasserkocher", "url": "https://www.medion.com/de/shop/kueche/wasserkocher"},
    {"name": "Toaster", "url": "https://www.medion.com/de/shop/kueche/toaster"},
    {"name": "Gaming Days", "url": "https://www.medion.com/at/shop/gaming-days"},
    {"name": "Mini Kühlschrank", "url": "https://www.medion.com/de/shop/kueche/mini-kuehlschraenke"},
    {"name": "Mikrowellen", "url": "https://www.medion.com/de/shop/kueche/mikrowellen"},
    {"name": "Kühlschränke", "url": "https://www.medion.com/de/shop/kueche/kuehlschraenke"},
    {"name": "Kühl- & Gefrierschränke", "url": "https://www.medion.com/de/shop/kueche/kuehl-gefrierschraenke"},
    {"name": "Kühlen & Gefrieren", "url": "https://www.medion.com/de/shop/kueche/kuehlen-gefrieren"},
    {"name": "Kühlboxen", "url": "https://www.medion.com/de/shop/kueche/kuehlboxen"},
    {"name": "Küchenmaschinen", "url": "https://www.medion.com/de/shop/kueche/kuechenmaschinen"},
    {"name": "Küchenkleingeräte", "url": "https://www.medion.com/de/shop/kueche/kuechenkleingeraete"},
    {"name": "Kochen & Zubereiten", "url": "https://www.medion.com/de/shop/kueche/kuechengeraete-kochen"},
    {"name": "Kaffeemaschinen", "url": "https://www.medion.com/de/shop/kueche/kaffeemaschinen"},
    {"name": "Induktionskochplatten", "url": "https://www.medion.com/de/shop/kueche/induktionskochplatten"},
    {"name": "HeiÃluftfritteuse mit zwei Kammern", "url": "https://www.medion.com/de/shop/kueche/heissluftfritteusen/doppelkammer"},
    {"name": "Alle Heissluftfritteusen", "url": "https://www.medion.com/de/shop/kueche/heissluftfritteusen"},
    {"name": "Grills", "url": "https://www.medion.com/de/shop/kueche/grills"},
    {"name": "Geschirrspüler", "url": "https://www.medion.com/de/shop/kueche/geschirrspueler"},
    {"name": "Gefrierschränke", "url": "https://www.medion.com/de/shop/kueche/gefrierschraenke"},
    {"name": "Eiswürfelmaschinen", "url": "https://www.medion.com/de/shop/kueche/eiswuerfelmaschinen"},
    {"name": "Eismaschinen", "url": "https://www.medion.com/de/shop/kueche/eismaschine"},
    {"name": "Brotbackautomaten", "url": "https://www.medion.com/de/shop/kueche/brotbackautomaten"},
    {"name": "Küchen-Angebote", "url": "https://www.medion.com/de/shop/kueche/angebote"},
    {"name": "Alle Küchengeräte", "url": "https://www.medion.com/de/shop/kueche/alle"},
    {"name": "Fitness & Gesundheit", "url": "https://www.medion.com/de/shop/koerperpflege-gesundheit"},
    {"name": "Kochen & Backen", "url": "https://www.medion.com/de/shop/kochen-backen"},
    {"name": "Klimageräte", "url": "https://www.medion.com/de/shop/klimageraete"},
    {"name": "Kabelloses Glätteisen HS2", "url": "https://www.medion.com/de/shop/kabelloses-glaetteisen-hs2"},
    {"name": "Inventur Sale", "url": "https://www.medion.com/at/shop/inventur-sale"},
    {"name": "Internetradios", "url": "https://www.medion.com/de/shop/internetradios"},
    {"name": "Intel Core Ultra Prozessoren", "url": "https://www.medion.com/de/shop/intel-core-ultra-series-2-produkte"},
    {"name": "Intel Core PCs", "url": "https://www.medion.com/de/shop/intel-core-pcs"},
    {"name": "Intel Core Gaming Laptops", "url": "https://www.medion.com/de/shop/intel-core-gaming-laptops"},
    {"name": "Intel 13 Alle", "url": "https://www.medion.com/de/shop/intel-13-alle"},
    {"name": "Hobby & Freizeit", "url": "https://www.medion.com/de/shop/hobby-und-freizeit"},
    {"name": "High End Gaming PCs", "url": "https://www.medion.com/de/shop/high-end-gaming-pc"},
    {"name": "High End Gaming Notebooks", "url": "https://www.medion.com/de/shop/high-end-gaming-notebooks"},
    {"name": "Heizen & Kühlen", "url": "https://www.medion.com/de/shop/heizen-kuehlen"},
    {"name": "Haushalt-Zubehör", "url": "https://www.medion.com/de/shop/haushalt-zubehoer"},
    {"name": "Alexa Haushalt", "url": "https://www.medion.com/de/shop/haushalt-alexa"},
    {"name": "zubehoer-p400-p350", "url": "https://www.medion.com/de/shop/haushalt/stielstaubsauger/zubehoer-p400-p350"},
    {"name": "Alle Reinigungsgeräte", "url": "https://www.medion.com/de/shop/haushalt/reinigungsgeraete"},
    {"name": "Polsterreiniger", "url": "https://www.medion.com/de/shop/haushalt/polsterreiniger"},
    {"name": "Overlock Nähmaschinen", "url": "https://www.medion.com/de/shop/haushalt/naehmaschinen/overlock"},
    {"name": "Freiarm Nähmaschinen", "url": "https://www.medion.com/de/shop/haushalt/naehmaschinen/freiarm"},
    {"name": "Digitale Nähmaschinen", "url": "https://www.medion.com/de/shop/haushalt/naehmaschinen/digital"},
    {"name": "Nähmaschinen", "url": "https://www.medion.com/de/shop/haushalt/naehmaschinen"},
    {"name": "luftentfeuchter", "url": "https://www.medion.com/de/shop/haushalt/heizen-kuehlen/luftentfeuchter"},
    {"name": "Alle Haushalt- und Freizeit-Produkte", "url": "https://www.medion.com/de/shop/haushalt/alle"},
    {"name": "Haushalt- & Freizeit-Angebote", "url": "https://www.medion.com/de/shop/haushalt/angebote"},
    {"name": "Alle Haushalt- und Freizeit-Produkte", "url": "https://www.medion.com/at/shop/haushalt-freizeit-alle"},
    {"name": "Handstaubsauger", "url": "https://www.medion.com/de/shop/handstaubsauger"},
    {"name": "Haartrockner LIFE HD2", "url": "https://www.medion.com/de/shop/haartrockner-life-hd2"},
    {"name": "Haartrockner", "url": "https://www.medion.com/de/shop/haarpflege/haartrockner"},
    {"name": "Glätteisen", "url": "https://www.medion.com/de/shop/haarpflege/glaetteisen"},
    {"name": "Glättbürsten", "url": "https://www.medion.com/de/shop/haarpflege/glaettbuersten"},
    {"name": "Haarpflege", "url": "https://www.medion.com/de/shop/haarpflege"},
    {"name": "Glätteisen LIFE HS1", "url": "https://www.medion.com/de/shop/glaetteisen-life-hs1"},
    {"name": "Geschenke bis 400 Euro", "url": "https://www.medion.com/de/shop/geschenke-bis-400-euro"},
    {"name": "Geschenke bis 250 Euro", "url": "https://www.medion.com/de/shop/geschenke-bis-250-euro"},
    {"name": "Geschenke bis 100 Euro", "url": "https://www.medion.com/de/shop/geschenke-bis-100-euro"},
    {"name": "Geschenke ab 400 Euro", "url": "https://www.medion.com/de/shop/geschenke-ab-400-euro"},
    {"name": "Garten Angebote", "url": "https://www.medion.com/de/shop/garten-angebote"},
    {"name": "Slush Eis Maschine", "url": "https://www.medion.com/at/shop/kueche/slush-eis-maschine"},
    {"name": "Gaming-Zubehör", "url": "https://www.medion.com/de/shop/gaming/zubehoer"},
    {"name": "Gaming-PCs", "url": "https://www.medion.com/de/shop/gaming/pc"},
    {"name": "Gaming-Monitore", "url": "https://www.medion.com/de/shop/gaming/monitor"},
    {"name": "Gaming-Laptops", "url": "https://www.medion.com/de/shop/gaming/laptop"},
    {"name": "Angebote Gaming", "url": "https://www.medion.com/de/shop/gaming/angebote"},
    {"name": "Alle Gaming Produkte", "url": "https://www.medion.com/de/shop/gaming/alle"},
    {"name": "Frühjahrsputz", "url": "https://www.medion.com/de/shop/fruehjahrsputz"},
    {"name": "weitere Modelle", "url": "https://www.medion.com/de/shop/fm-radios"},
    {"name": "Festival", "url": "https://www.medion.com/de/shop/festival"},
    {"name": "Heimkinosystem", "url": "https://www.medion.com/de/shop/entertainment"},
    {"name": "Einsteiger PC", "url": "https://www.medion.com/de/shop/einsteiger-pc"},
    {"name": "DAB Radios", "url": "https://www.medion.com/de/shop/dab-radios"},
    {"name": "Core Gaming PCs", "url": "https://www.medion.com/de/shop/core-gaming-pc"},
    {"name": "Core Gaming Notebooks", "url": "https://www.medion.com/de/shop/core-gaming-notebooks"},
    {"name": "Camping", "url": "https://www.medion.com/de/shop/camping"},
    {"name": "Back to Uni Tablet", "url": "https://www.medion.com/de/shop/btu-tablets"},
    {"name": "Back to Uni Radio", "url": "https://www.medion.com/de/shop/btu-radios"},
    {"name": "Back to Uni Frühstück", "url": "https://www.medion.com/de/shop/btu-fruehstuecken"},
    {"name": "Back to Uni Freizeit", "url": "https://www.medion.com/de/shop/btu-freizeit"},
    {"name": "Bodenreiniger", "url": "https://www.medion.com/de/shop/bodenreiniger"},
    {"name": "Bluetooth Lautsprecher", "url": "https://www.medion.com/de/shop/bluetooth-lautsprecher"},
    {"name": "Back to School", "url": "https://www.medion.com/de/shop/back-to-school"},
    {"name": "Wecker", "url": "https://www.medion.com/de/shop/audio/wecker"},
    {"name": "Radios", "url": "https://www.medion.com/de/shop/audio/radio"},
    {"name": "Partylautsprecher", "url": "https://www.medion.com/de/shop/audio/partylautsprecher"},
    {"name": "Audio-Systeme", "url": "https://www.medion.com/de/shop/audio/musikanlagen"},
    {"name": "Lautsprecher", "url": "https://www.medion.com/de/shop/audio/lautsprecher"},
    {"name": "Küchen-unterbauradio", "url": "https://www.medion.com/de/shop/audio/kuechenunterbauradios"},
    {"name": "Kopfhörer", "url": "https://www.medion.com/de/shop/audio/kopfhoerer"},
    {"name": "Boomboxen", "url": "https://www.medion.com/de/shop/audio/boomboxen"},
    {"name": "Bluetooth Kopfhörer", "url": "https://www.medion.com/de/shop/audio/bluetooth-kopfhoerer"},
    {"name": "Baustellenradio", "url": "https://www.medion.com/de/shop/audio/baustellenradio"},
    {"name": "Angebote Audio", "url": "https://www.medion.com/de/shop/audio/angebote"},
    {"name": "Alle Audio Produkte", "url": "https://www.medion.com/de/shop/audio/alle"},
    {"name": "Angebote bei MEDION", "url": "https://www.medion.com/de/shop/angebote"},
    {"name": "Alexa", "url": "https://www.medion.com/de/shop/alexa"},
    {"name": "Akoya PCs", "url": "https://www.medion.com/de/shop/akoya-pcs"},
    {"name": "Akku-Stielstaubsauger", "url": "https://www.medion.com/de/shop/akku-stielstaubsauger"},
    {"name": "Zyklon Staubsauger", "url": "https://www.medion.com/at/shop/zyklon-staubsauger"},
    {"name": "Work from Home PCs", "url": "https://www.medion.com/at/shop/work-from-home-pcs"},
    {"name": "work-from-home-alle", "url": "https://www.medion.com/at/shop/work-from-home-alle"},
    {"name": "Saugroboter", "url": "https://www.medion.com/de/shop/saugroboter/saugroboter-wischroboter"},
    {"name": "Saugroboter", "url": "https://www.medion.com/at/shop/saugroboter-wischroboter"},
    {"name": "Windows Update", "url": "https://www.medion.com/at/shop/windows-update"},
    {"name": "Versandkostenfrei", "url": "https://www.medion.com/at/shop/versandkostenfrei"},
    {"name": "Ventilatoren & Klimageräte", "url": "https://www.medion.com/at/shop/ventilatoren-klimageraete"},
    {"name": "Ventilatoren", "url": "https://www.medion.com/at/shop/ventilatoren"},
    {"name": "TV Kaufberater Auflösungen", "url": "https://www.medion.com/at/shop/tv-hd-fhd-uhd"},
    {"name": "TV Kaufberater Hintergrundbeleuchtung", "url": "https://www.medion.com/at/shop/tv-edge-led-direct-led"},
    {"name": "Vidaa TVs", "url": "https://www.medion.com/at/shop/tv/vidaa"},
    {"name": "TV-Soundbars", "url": "https://www.medion.com/at/shop/tv/soundbars"},
    {"name": "Smart TV", "url": "https://www.medion.com/at/shop/tv/smart-tv"},
    {"name": "QLED TVs", "url": "https://www.medion.com/at/shop/tv/qled"},
    {"name": "Premium-TVs", "url": "https://www.medion.com/at/shop/tv/premium"},
    {"name": "OLED TVs", "url": "https://www.medion.com/at/shop/tv/oled"},
    {"name": "TVs mit Soundbar", "url": "https://www.medion.com/at/shop/tv/mit-soundbar"},
    {"name": "Mobilen TVs", "url": "https://www.medion.com/at/shop/tv/mini"},
    {"name": "TV Kaufberater Micro Dimming", "url": "https://www.medion.com/at/shop/tv/micro-dimming"},
    {"name": "TV HDR", "url": "https://www.medion.com/at/shop/tv/hdr"},
    {"name": "HD TVs", "url": "https://www.medion.com/at/shop/tv/hd"},
    {"name": "Fire TVs", "url": "https://www.medion.com/at/shop/tv/fire-tv"},
    {"name": "FHD TVs", "url": "https://www.medion.com/at/shop/tv/fhd"},
    {"name": "Einsteiger", "url": "https://www.medion.com/at/shop/tv/einsteiger"},
    {"name": "TV Dolby Vision", "url": "https://www.medion.com/at/shop/tv/dolby-vision"},
    {"name": "bis ca. 80 cm (32'')", "url": "https://www.medion.com/at/shop/tv/bis-32-zoll"},
    {"name": "TV Angebote", "url": "https://www.medion.com/at/shop/tv/angebote"},
    {"name": "Android TVs", "url": "https://www.medion.com/at/shop/tv/android-tv"},
    {"name": "4K UHD TVs", "url": "https://www.medion.com/at/shop/tv/4k-uhd"},
    {"name": "ca. 98 cm - 126 cm (39in bis 50in)", "url": "https://www.medion.com/at/shop/tv/39-bis-50-zoll"},
    {"name": "Alle TVs", "url": "https://www.medion.com/at/shop/tv"},
    {"name": "Turmventilatoren", "url": "https://www.medion.com/at/shop/turmventilatoren"},
    {"name": "Topseller", "url": "https://www.medion.com/at/shop/topseller"},
    {"name": "Mäuse und Tastaturen", "url": "https://www.medion.com/at/shop/tastaturen-und-maeuse"},
    {"name": "Alle Tablets", "url": "https://www.medion.com/at/shop/tablets-alle"},
    {"name": "Staubsauger", "url": "https://www.medion.com/at/shop/staubsauger-alle"},
    {"name": "Sportliche Angebote", "url": "https://www.medion.com/at/shop/sportliche-angebote"},
    {"name": "Sommer Angebote", "url": "https://www.medion.com/at/shop/sommer-angebote"},
    {"name": "Saugroboter X-Serie", "url": "https://www.medion.com/de/shop/saugroboter/saugroboter-x-serie"},
    {"name": "Smarte Produkte alle", "url": "https://www.medion.com/at/shop/smarte-produkte-alle"},
    {"name": "Saugroboter X-Serie", "url": "https://www.medion.com/at/shop/saugroboter-x-serie"},
    {"name": "zubehoer-x50", "url": "https://www.medion.com/de/shop/saugroboter/zubehoer-x50"},
    {"name": "zubehoer-x41-x42", "url": "https://www.medion.com/de/shop/saugroboter/zubehoer-x41-x42"},
    {"name": "zubehoer-x40", "url": "https://www.medion.com/de/shop/saugroboter/zubehoer-x40"},
    {"name": "zubehoer-x20", "url": "https://www.medion.com/de/shop/saugroboter/zubehoer-x20"},
    {"name": "zubehoer-x10", "url": "https://www.medion.com/de/shop/saugroboter/zubehoer-x10"},
    {"name": "zubehoer-s40", "url": "https://www.medion.com/de/shop/saugroboter/zubehoer-s40"},
    {"name": "zubehoer-s35", "url": "https://www.medion.com/de/shop/saugroboter/zubehoer-s35"},
    {"name": "zubehoer-s30", "url": "https://www.medion.com/de/shop/saugroboter/zubehoer-s30"},
    {"name": "zubehoer-s20", "url": "https://www.medion.com/de/shop/saugroboter/zubehoer-s20"},
    {"name": "zubehoer-s05", "url": "https://www.medion.com/de/shop/saugroboter/zubehoer-s05"},
    {"name": "Saugroboter-Zubehör", "url": "https://www.medion.com/de/shop/saugroboter-zubehoer"},
    {"name": "Saugroboter-Zubehör", "url": "https://www.medion.com/at/shop/saugroboter-zubehoer"},
    {"name": "Saugroboter mit Wischfunktion", "url": "https://www.medion.com/de/shop/saug-wischroboter"},
    {"name": "Saugroboter mit Wischfunktion", "url": "https://www.medion.com/at/shop/saug-wischroboter"},
    {"name": "Rückgaberecht", "url": "https://www.medion.com/at/shop/rueckgaberecht"},
    {"name": "Radios", "url": "https://www.medion.com/at/shop/radios"},
    {"name": "QLED OLED TVs", "url": "https://www.medion.com/at/shop/qled-oled-tvs"},
    {"name": "Performance-Fernseher", "url": "https://www.medion.com/at/shop/performance-fernseher"},
    {"name": "Gaming-PCs", "url": "https://www.medion.com/at/shop/pc-gamer"},
    {"name": "PC-Angebote", "url": "https://www.medion.com/at/shop/pc/angebote"},
    {"name": "Partylautsprecher", "url": "https://www.medion.com/at/shop/partylautsprecher"},
    {"name": "Party", "url": "https://www.medion.com/at/shop/party"},
    {"name": "Nvidia 50er Serie Produkte", "url": "https://www.medion.com/at/shop/nvidia-rtx-serie-50"},
    {"name": "NVIDIA RTX Produkte", "url": "https://www.medion.com/at/shop/nvidia-rtx-produkte"},
    {"name": "NVIDIA RTX Laptops", "url": "https://www.medion.com/at/shop/nvidia-rtx-laptops"},
    {"name": "Nvidia rtx", "url": "https://www.medion.com/at/shop/nvidia-rtx"},
    {"name": "NVIDIA PC", "url": "https://www.medion.com/at/shop/nvidia-pc"},
    {"name": "Neuheiten", "url": "https://www.medion.com/at/shop/neuheiten"},
    {"name": "Nähmaschinen", "url": "https://www.medion.com/at/shop/naehmaschinen"},
    {"name": "Nähmaschine", "url": "https://www.medion.com/at/shop/naehmaschine"},
    {"name": "Audio-Systeme", "url": "https://www.medion.com/at/shop/musikanlagen"},
    {"name": "Multimedia-PC", "url": "https://www.medion.com/at/shop/multimedia-pc"},
    {"name": "Monitor-Angebote", "url": "https://www.medion.com/at/shop/monitore/angebote"},
    {"name": "Monitore", "url": "https://www.medion.com/at/shop/monitore"},
    {"name": "Mini PCs", "url": "https://www.medion.com/at/shop/mini-pcs"},
    {"name": "Microsoft Jumpstart Gaming", "url": "https://www.medion.com/at/shop/microsoft-jumpstart-gaming"},
    {"name": "Microsoft Jumpstart", "url": "https://www.medion.com/at/shop/microsoft-jumpstart"},
    {"name": "Luftreiniger Alle", "url": "https://www.medion.com/at/shop/luftreiniger-alle"},
    {"name": "Laptop & PC Week", "url": "https://www.medion.com/at/shop/lp/laptop-pc-week"},
    {"name": "Intel Produkte", "url": "https://www.medion.com/at/shop/lp/intel-produkte"},
    {"name": "Intel PC", "url": "https://www.medion.com/at/shop/lp/intel-pc"},
    {"name": "Intel Games Bundle Produkte", "url": "https://www.medion.com/at/shop/lp/intel-games-bundle-produkte"},
    {"name": "Lieferung bis Weihnachten", "url": "https://www.medion.com/at/shop/lieferung-bis-weihnachten"},
    {"name": "Lenovo Produkte", "url": "https://www.medion.com/at/shop/lenovo-produkte"},
    {"name": "Lautsprecher", "url": "https://www.medion.com/at/shop/lautsprecher"},
    {"name": "Laptop-Zubehör", "url": "https://www.medion.com/at/shop/laptops/zubehoer"},
    {"name": "SPRCHRGD Laptops", "url": "https://www.medion.com/at/shop/laptops/sprchrgd"},
    {"name": "Multimedia-Laptops", "url": "https://www.medion.com/at/shop/laptops/multimedia"},
    {"name": "KI gestützte Laptops", "url": "https://www.medion.com/at/shop/laptops/ki"},
    {"name": "Intel Core i7", "url": "https://www.medion.com/at/shop/laptops/intel-core-i7"},
    {"name": "Intel Core i5", "url": "https://www.medion.com/at/shop/laptops/intel-core-i5"},
    {"name": "Intel Core Laptops", "url": "https://www.medion.com/at/shop/laptops/intel-core"},
    {"name": "Homeoffice Laptops", "url": "https://www.medion.com/at/shop/laptops/homeoffice"},
    {"name": "Einsteiger-Laptops", "url": "https://www.medion.com/at/shop/laptops/einsteiger"},
    {"name": "Laptops Angebote", "url": "https://www.medion.com/at/shop/laptops/angebote"},
    {"name": "AMD Ryzen", "url": "https://www.medion.com/at/shop/laptops/amd-ryzen"},
    {"name": "18'' Laptops", "url": "https://www.medion.com/at/shop/laptops/18-zoll"},
    {"name": "17'' Laptops", "url": "https://www.medion.com/at/shop/laptops/17-zoll"},
    {"name": "16'' Laptops", "url": "https://www.medion.com/at/shop/laptops/16-zoll"},
    {"name": "15'' Laptops", "url": "https://www.medion.com/at/shop/laptops/15-zoll"},
    {"name": "14'' Laptops", "url": "https://www.medion.com/at/shop/laptops/14-zoll"},
    {"name": "Alle Laptops", "url": "https://www.medion.com/at/shop/laptops"},
    {"name": "Kühlen & Gefrieren", "url": "https://www.medion.com/at/shop/kuehlen-gefrieren"},
    {"name": "Küchenkleingeräte", "url": "https://www.medion.com/at/shop/kuechenkleingeraete"},
    {"name": "Reinigungsgeräte", "url": "https://www.medion.com/at/shop/kuechengeraete-reinigung"},
    {"name": "Kochen & Zubereiten", "url": "https://www.medion.com/at/shop/kuechengeraete-kochen"},
    {"name": "Frühstück", "url": "https://www.medion.com/at/shop/kuechengeraete-fruehstueck"},
    {"name": "Wasserkocher", "url": "https://www.medion.com/at/shop/kueche/wasserkocher"},
    {"name": "Toaster", "url": "https://www.medion.com/at/shop/kueche/toaster"},
    {"name": "Mini-Kühlschrank", "url": "https://www.medion.com/at/shop/kueche/mini-kuehlschraenke"},
    {"name": "Mikrowellen", "url": "https://www.medion.com/at/shop/kueche/mikrowellen"},
    {"name": "Kühlschränke", "url": "https://www.medion.com/at/shop/kueche/kuehlschraenke"},
    {"name": "Kühl- & Gefrierschränke", "url": "https://www.medion.com/at/shop/kueche/kuehl-gefrierschraenke"},
    {"name": "Küchenmaschinen", "url": "https://www.medion.com/at/shop/kueche/kuechenmaschinen"},
    {"name": "Kaffeemaschinen", "url": "https://www.medion.com/at/shop/kueche/kaffeemaschinen"},
    {"name": "Induktionskochplatten", "url": "https://www.medion.com/at/shop/kueche/induktionskochplatten"},
    {"name": "doppelkammer", "url": "https://www.medion.com/at/shop/kueche/heissluftfritteusen/doppelkammer"},
    {"name": "Heissluftfritteusen Produkte", "url": "https://www.medion.com/at/shop/kueche/heissluftfritteusen"},
    {"name": "Grills", "url": "https://www.medion.com/at/shop/kueche/grills"},
    {"name": "Gefrierschränke", "url": "https://www.medion.com/at/shop/kueche/gefrierschraenke"},
    {"name": "Eiswürfelmaschinen", "url": "https://www.medion.com/at/shop/kueche/eiswuerfelmaschinen"},
    {"name": "Brotbackautomaten", "url": "https://www.medion.com/at/shop/kueche/brotbackautomaten"},
    {"name": "Küchen-Angebote", "url": "https://www.medion.com/at/shop/kueche/angebote"},
    {"name": "Alle Küchengeräte", "url": "https://www.medion.com/at/shop/kueche/alle"},
    {"name": "Küchen-Produkte", "url": "https://www.medion.com/at/shop/kueche"},
    {"name": "Kopfhörer", "url": "https://www.medion.com/at/shop/kopfhoerer"},
    {"name": "Fitness & Gesundheit", "url": "https://www.medion.com/at/shop/koerperpflege-gesundheit"},
    {"name": "Kochen & Backen", "url": "https://www.medion.com/at/shop/kochen-backen"},
    {"name": "Klimageräte", "url": "https://www.medion.com/at/shop/klimageraete"},
    {"name": "Wecker", "url": "https://www.medion.com/at/shop/kategorie-wecker"},
    {"name": "Inventur Sale", "url": "https://www.medion.com/de/shop/inventur-sale"},
    {"name": "Internetradios", "url": "https://www.medion.com/at/shop/internetradios"},
    {"name": "Intel Core Ultra Prozessoren", "url": "https://www.medion.com/at/shop/intel-core-ultra-series-2-produkte"},
    {"name": "Intel Core PCs", "url": "https://www.medion.com/at/shop/intel-core-pcs"},
    {"name": "Intel Core Gaming Laptops", "url": "https://www.medion.com/at/shop/intel-core-gaming-laptops"},
    {"name": "Intel 13 Alle", "url": "https://www.medion.com/at/shop/intel-13-alle"},
    {"name": "Hobby & Freizeit", "url": "https://www.medion.com/at/shop/hobby-und-freizeit"},
    {"name": "High End Gaming PCs", "url": "https://www.medion.com/at/shop/high-end-gaming-pc"},
    {"name": "High End Gaming Notebooks", "url": "https://www.medion.com/at/shop/high-end-gaming-notebooks"},
    {"name": "Heizen & Kühlen", "url": "https://www.medion.com/at/shop/heizen-kuehlen"},
    {"name": "Haushalt-Zubehör", "url": "https://www.medion.com/at/shop/haushalt-zubehoer"},
    {"name": "Alexa Haushalt", "url": "https://www.medion.com/at/shop/haushalt-alexa"},
    {"name": "Alle Reinigungsgeräte", "url": "https://www.medion.com/at/shop/haushalt/reinigungsgeraete"},
    {"name": "Polsterreiniger", "url": "https://www.medion.com/at/shop/haushalt/polsterreiniger"},
    {"name": "Overlock Nähmaschinen", "url": "https://www.medion.com/at/shop/haushalt/naehmaschinen/overlock"},
    {"name": "Freiarm Nähmaschinen", "url": "https://www.medion.com/at/shop/haushalt/naehmaschinen/freiarm"},
    {"name": "Digitale Nähmaschinen", "url": "https://www.medion.com/at/shop/haushalt/naehmaschinen/digital"},
    {"name": "Luftentfeuchter", "url": "https://www.medion.com/at/shop/haushalt/luftentfeuchter"},
    {"name": "Kühlboxen", "url": "https://www.medion.com/at/shop/haushalt/kuehlboxen"},
    {"name": "Haushalt- & Freizeit-Angebote", "url": "https://www.medion.com/at/shop/haushalt/angebote"},
    {"name": "Handstaubsauger", "url": "https://www.medion.com/at/shop/handstaubsauger"},
    {"name": "Haartrockner", "url": "https://www.medion.com/at/shop/haarpflege/haartrockner"},
    {"name": "Glätteisen", "url": "https://www.medion.com/at/shop/haarpflege/glaetteisen"},
    {"name": "Glättbürsten", "url": "https://www.medion.com/at/shop/haarpflege/glaettbuersten"},
    {"name": "Haarpflege", "url": "https://www.medion.com/at/shop/haarpflege"},
    {"name": "Geschirrspüler", "url": "https://www.medion.com/at/shop/geschirrspueler"},
    {"name": "Geschenke bis 400 Euro", "url": "https://www.medion.com/at/shop/geschenke-bis-400-euro"},
    {"name": "Geschenke bis 250in", "url": "https://www.medion.com/at/shop/geschenke-bis-250-euro"},
    {"name": "Geschenke bis 100in", "url": "https://www.medion.com/at/shop/geschenke-bis-100-euro"},
    {"name": "Geschenke ab 400 Euro", "url": "https://www.medion.com/at/shop/geschenke-ab-400-euro"},
    {"name": "Garten Angebote", "url": "https://www.medion.com/at/shop/garten-angebote"},
    {"name": "Garantierte Lieferung", "url": "https://www.medion.com/at/shop/garantierte-lieferung"},
    {"name": "Gaming-Zubehör", "url": "https://www.medion.com/at/shop/gaming-zubehoer"},
    {"name": "Gaming-Monitore", "url": "https://www.medion.com/at/shop/gaming-monitore"},
    {"name": "Slush Eis Maschine", "url": "https://www.medion.com/de/shop/kueche/slush-eis-maschine"},
    {"name": "Alle Gaming Produkte", "url": "https://www.medion.com/at/shop/gaming-alle"},
    {"name": "Gaming-Laptops", "url": "https://www.medion.com/at/shop/gaming/laptop"},
    {"name": "Gaming Angebote", "url": "https://www.medion.com/at/shop/gaming/angebote"},
    {"name": "Frühjahrsputz", "url": "https://www.medion.com/at/shop/fruehjahrsputz"},
    {"name": "weitere Modelle", "url": "https://www.medion.com/at/shop/fm-radios"},
    {"name": "Festival", "url": "https://www.medion.com/at/shop/festival"},
    {"name": "Heimkinosystem", "url": "https://www.medion.com/at/shop/entertainment"},
    {"name": "Eismaschinen", "url": "https://www.medion.com/at/shop/eismaschinen"},
    {"name": "Einsteiger PC", "url": "https://www.medion.com/at/shop/einsteiger-pc"},
    {"name": "Drucker & Patronen", "url": "https://www.medion.com/at/shop/drucker"},
    {"name": "Desktop-PCs", "url": "https://www.medion.com/at/shop/desktop-pcs"},
    {"name": "DAB Radios", "url": "https://www.medion.com/at/shop/dab-radios"},
    {"name": "Core Gaming PCs", "url": "https://www.medion.com/at/shop/core-gaming-pc"},
    {"name": "Core Gaming Notebooks", "url": "https://www.medion.com/at/shop/core-gaming-notebooks"},
    {"name": "PC-Zubehör", "url": "https://www.medion.com/at/shop/computer-zubehoer"},
    {"name": "Camping", "url": "https://www.medion.com/at/shop/camping"},
    {"name": "Back to Uni Tablet", "url": "https://www.medion.com/at/shop/btu-tablets"},
    {"name": "Back to Uni Radio", "url": "https://www.medion.com/at/shop/btu-radios"},
    {"name": "Back to Uni Frühstück", "url": "https://www.medion.com/at/shop/btu-fruehstuecken"},
    {"name": "Back to Uni Freizeit", "url": "https://www.medion.com/at/shop/btu-freizeit"},
    {"name": "Bodenreiniger", "url": "https://www.medion.com/at/shop/bodenreiniger"},
    {"name": "Bluetooth Lautsprecher", "url": "https://www.medion.com/at/shop/bluetooth-lautsprecher"},
    {"name": "Back to School", "url": "https://www.medion.com/at/shop/back-to-school"},
    {"name": "Alle Audio Produkte", "url": "https://www.medion.com/at/shop/audio-alle"},
    {"name": "Bluetooth-Kopfhörer", "url": "https://www.medion.com/at/shop/audio/bluetooth-kopfhoerer"},
    {"name": "Audio Angebote", "url": "https://www.medion.com/at/shop/audio/angebote"},
    {"name": "Angebote bei MEDION", "url": "https://www.medion.com/at/shop/angebote"},
    {"name": "All-in-One-PCs", "url": "https://www.medion.com/at/shop/all-in-one-pc"},
    {"name": "Alle PCs", "url": "https://www.medion.com/at/shop/alle-pcs"},
    {"name": "Alexa", "url": "https://www.medion.com/at/shop/alexa"},
    {"name": "Akoya PCs", "url": "https://www.medion.com/at/shop/akoya-pcs"},
    {"name": "Akku-Stielstaubsauger", "url": "https://www.medion.com/at/shop/akku-stielstaubsauger"},
    {"name": "Blue Days", "url": "https://www.medion.com/at/shop/blue-days"},
    {"name": "Weekend-Sale", "url": "https://www.medion.com/at/shop/weekend-sale"},
    {"name": "Blue Days", "url": "https://www.medion.com/de/shop/blue-days"},
    {"name": "Gaming Days", "url": "https://www.medion.com/de/shop/gaming-days"},
    {"name": "Weekend Sale", "url": "https://www.medion.com/de/shop/weekend-sale"},]

# matches "Produkte" or "Produkt"
COUNT_PATTERN = re.compile(
    r"(\d[\d.,]*)\s*(?:Produkte?|Produkt?)",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

TSV_PATH = os.path.join(os.path.dirname(__file__), "data", "product_count_log.tsv")
SUMMARY_TSV_PATH = os.path.join(
    os.path.dirname(__file__), "data", "product_count_summary.tsv"
)
LEGACY_CSV_PATH = os.path.join(
    os.path.dirname(__file__), "data", "product_count_log.csv"
)
LEGACY_SUMMARY_CSV_PATH = os.path.join(
    os.path.dirname(__file__), "data", "product_count_summary.csv"
)

# Workaround for the full-catalog fallback bug: any raw count above this
# threshold is treated as that fallback and logged as 0, EXCEPT the URLs
# listed below, which are known to legitimately have large product counts.
SENTINEL_THRESHOLD = 150

KNOWN_LARGE_CATALOG_URLS = {
    "https://www.medion.com/at/shop/angebote",
    "https://www.medion.com/at/shop/geschenke-bis-100-euro",
    "https://www.medion.com/at/shop/geschenke-bis-250-euro",
    "https://www.medion.com/at/shop/versandkostenfrei",
    "https://www.medion.com/de/shop/angebote",
    "https://www.medion.com/de/shop/geschenke-bis-100-euro",
    "https://www.medion.com/de/shop/geschenke-bis-250-euro",
    "https://www.medion.com/de/shop/paypal-null-prozent-finanzierung",
    "https://www.medion.com/de/shop/versandkostenfrei",}


def get_product_count(url: str):
    """Fetch a page and pull out the first number matching COUNT_PATTERN."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        return None, f"ERROR: {e}"

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    match = COUNT_PATTERN.search(text)

    if not match:
        return None, "NOT_FOUND"

    raw = match.group(1).replace(".", "").replace(",", "")
    try:
        return int(raw), "OK"
    except ValueError:
        return None, "PARSE_ERROR"


def run_check() -> pd.DataFrame:
    now_local = datetime.now(LOCAL_TZ)
    timestamp = now_local.strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for entry in URLS:
        count, status = get_product_count(entry["url"])
        rows.append({
            "timestamp_CEST": timestamp,
            "name": entry["name"],
            "url": entry["url"],
            "raw_product_count": count,
            "status": status,
        })
    df = pd.DataFrame(rows)

    # ---- Detect and zero-out the "show everything" fallback ----
    df["product_count"] = df["raw_product_count"]
    df["is_sentinel"] = (df["raw_product_count"] > SENTINEL_THRESHOLD) & (
        ~df["url"].isin(KNOWN_LARGE_CATALOG_URLS)
    )
    df.loc[df["is_sentinel"], "product_count"] = 0

    # Nullable integer dtype so whole numbers never render as "22.0"
    df["raw_product_count"] = df["raw_product_count"].astype("Int64")
    df["product_count"] = df["product_count"].astype("Int64")

    return df


def normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    """Migrate old timestamps to an Excel-friendly, timezone-free value."""
    if "timestamp" in df.columns and "timestamp_CEST" not in df.columns:
        df = df.rename(columns={"timestamp": "timestamp_CEST"})

    if "timestamp_CEST" in df.columns:
        df["timestamp_CEST"] = (
            df["timestamp_CEST"]
            .astype("string")
            .str.replace(r"\s+(?:CEST|CET)$", "", regex=True)
        )

    return df


def build_summary(df_all: pd.DataFrame) -> pd.DataFrame:
    """Return lifetime average and latest product count for every URL."""
    latest = (
        df_all.sort_values("timestamp_CEST")
        .groupby("url", as_index=False, sort=False)
        .tail(1)[["name", "url", "product_count", "timestamp_CEST"]]
        .rename(columns={
            "product_count": "latest_product_count",
            "timestamp_CEST": "latest_timestamp_CEST",
        })
    )
    averages = (
        df_all.groupby("url", as_index=False, sort=False)["product_count"]
        .mean()
        .rename(columns={"product_count": "average_product_count"})
    )
    summary = latest.merge(averages, on="url", how="left")
    summary = summary[[
        "name",
        "url",
        "average_product_count",
        "latest_product_count",
        "latest_timestamp_CEST",
    ]]
    summary["average_product_count"] = summary["average_product_count"].round(2)
    summary["latest_product_count"] = summary["latest_product_count"].astype("Int64")
    return summary.sort_values(["name", "url"], kind="stable")


def main():
    os.makedirs(os.path.dirname(TSV_PATH), exist_ok=True)
    if os.path.exists(TSV_PATH):
        df_old = pd.read_csv(TSV_PATH, sep="\t", decimal=",")
    elif os.path.exists(LEGACY_CSV_PATH):
        # One-time migration: preserve the young CSV history when switching to TSV.
        df_old = pd.read_csv(LEGACY_CSV_PATH)
    else:
        df_old = pd.DataFrame()
    df_old = normalize_history(df_old)
    if not df_old.empty:
        df_old["product_count"] = df_old["product_count"].astype("Int64")

    df_new = run_check()
    df_all = pd.concat([df_old, df_new], ignore_index=True) if not df_old.empty else df_new
    df_all.to_csv(
        TSV_PATH,
        index=False,
        sep="\t",
        decimal=",",
        encoding="utf-8-sig",
    )
    build_summary(df_all).to_csv(
        SUMMARY_TSV_PATH,
        index=False,
        sep="\t",
        decimal=",",
        encoding="utf-8-sig",
    )

    # Remove superseded CSVs only after both TSV exports succeed.
    for legacy_path in (LEGACY_CSV_PATH, LEGACY_SUMMARY_CSV_PATH):
        if os.path.exists(legacy_path):
            os.remove(legacy_path)

    # ---- Readable summary for the Actions "Summary" tab ----
    lines = ["# Product Count Check", "", "| Name | URL | Count | Raw | Status |", "|---|---|---|---|---|"]
    for _, row in df_new.iterrows():
        lines.append(
            f"| {row['name']} | {row['url']} | {row['product_count']} | {row['raw_product_count']} | {row['status']} |"
        )

    # ---- Detect 0 <-> non-zero transitions vs. the previous run, per URL ----
    alert_lines = []
    if not df_old.empty:
        for url in df_new["url"].unique():
            prev = df_old[df_old["url"] == url].tail(1)
            curr = df_new[df_new["url"] == url].tail(1)
            if prev.empty or curr.empty:
                continue
            prev_count = prev["product_count"].values[0]
            curr_count = curr["product_count"].values[0]
            if pd.isna(prev_count) or pd.isna(curr_count):
                continue
            prev_zero = prev_count == 0
            curr_zero = curr_count == 0
            if prev_zero != curr_zero:
                name = curr["name"].values[0]
                direction = "went OUT OF STOCK (0 products)" if curr_zero else "is BACK IN STOCK"
                alert_lines.append(f"- **{name}** ({url}): {direction} (was {int(prev_count)}, now {int(curr_count)})")

    lines.append("")
    lines.append("## Changes vs. previous run")
    lines.extend(alert_lines if alert_lines else ["No 0/non-zero changes detected."])

    summary = "\n".join(lines)
    print(summary)

    step_summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_file:
        with open(step_summary_file, "a") as f:
            f.write(summary + "\n")

    # ---- Hand off to the workflow: only trigger the email step if something changed ----
    changed = bool(alert_lines)
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"changed={'true' if changed else 'false'}\n")

    if changed:
        with open("alert_body.txt", "w") as f:
            f.write("The following listing pages changed stock status:\n\n")
            f.write("\n".join(alert_lines))


if __name__ == "__main__":
    main()
