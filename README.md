# Hollandse Luchten

## Developer Quick Start

- **Frontend (Zero-build HTML/CSS/JS)**: See **[frontend/README.md](frontend/README.md)**
  ```bash
  python3 -m http.server 8080 --bind 127.0.0.1 --directory frontend
  # Open http://localhost:8080/ (address check) or http://localhost:8080/gesprek/ (chat)
  ```
- **Backend (FastAPI + R/Parquet REST API on port 8000)**: See **[backend/API.md](backend/API.md)**
  > **The backend needs R and a clone of [Analyse-Together](https://github.com/rivm-syso/Analyse-Together) next to this
  > repo.** The calculations call the validated R functions from that repo; there is no Python substitute. Without R or
  > the clone, every analysis endpoint answers `503` ("R is not installed" / "Analyse-Together checkout not found").
  > Setup: see "Required project structure" in [backend/API.md](backend/API.md).
- **Live Public Demo**: [https://hollandse-luchten-analyse.web.app/adres.html](https://hollandse-luchten-analyse.web.app/adres.html)

---

[Who is who?](https://gemini.google.com/app/d9a55ca4bfe6de50)
* [Luchtmeetnet](https://www.luchtmeetnet.nl): het officiële meetnetwerk van het RIVM met dure sensoren
* [Samen Meten](https://www.samenmeten.nl): verzamelt data afkomstig van goedkopere consumentensensoren
* [SODAQ](https://knowyourair.net): bedrijf dat (mobiele) fijnstofmeters maakt
* [Hollandse Luchten](https://hollandse-luchten.org): 
  * Koopt en distribueert apparatuur onder burgers
  * Grote toeleverancier van meetdata voor het Samen Meten-platform 

## [Tools](https://hollandse-luchten.org/tools)

### [1. Samen Analyseren Tool](https://analyseren.samenmeten.nl/)
Web UI voor het downloaden en analyseren van Samen Meten sensordata.
Deze sensordata kan gecombineerd worden met referentiemeetdata van het Landelijk Luchtmeetnet en met de weergegevens van het KNMI.
Uitgangspunt van sensordata van Samen Meten is dat het burgerwetenschap is en geen officiele meting.

Gedownloade data bevat ruwe én gekalibreerde data.
De kalibratie van sensordata wordt gedaan met behulp van secundaire data die niet altijd beschikbaar zijn. 
Het kan daarom voorkomen dat voor sommige tijdsperioden geen gekalibreerde waarden in de database aanwezig zijn.

In de Samen Analyseren Tool kun je het verschil tussen ruwe en gekalibreerde sensormetingen zien als een lichtgekleurde band om de meetwaardes heen.
Er blijft een meetonzekerheid over voor de gekalibreerde waardes, bijvoorbeeld omdat alle sensoren een klein beetje anders reageren op de hoeveelheid fijnstof in de lucht.
De meetonzekerheid van een sensor is geschat op 20% van de meetwaarde. Als de meetwaardes heel laag zijn wordt 20% daarvan ook heel klein, daarom hebben we ook een minimale onzekerheid geschat van 5,3 μg/m³ voor pm2,5 en 8,5 μg/m³ voor pm10.

Zie ook [samen-analyseren-tool.txt](docs/samen-analyseren-tool.txt) voor meer details

Een uitgebreide handleiding is [hier](https://www.samenmeten.nl/dataportaal/samen-analyseren-tool) te vinden.
Uitgebreide uitleg kalibratie is [hier](https://www.samenmeten.nl/dataportaal/kalibratie-van-fijnstofsensoren) te vinden.

### [2. Samen Meten API](https://www.samenmeten.nl/dataportaal/api-application-programming-interface)

https://www.samenmeten.nl/dataportaal

* **Things:** hiermee worden fysieke objecten bedoeld. In ons geval de complete meetsystemen. Verwarrend is dat wij dat meestal de sensor noemen.
* **Sensors:** het specifieke meetapparaat dat iets bepaalds (PM10, NO2, Temperatuur) meet. Een Thing kan dus meerdere Sensors bevatten.
* **Observations:** de meetwaarde gemeten door een bepaalde Sensor in een bepaald Thing op een bepaalde tijd.

**Links:**
* [API](https://api-samenmeten.rivm.nl/v1.0)
* [API reference docs](https://gost1.docs.apiary.io/#reference/0/root/get-sensorthings-resource-endpoints)

samenmeten.rivm.nl is verplaatst naar samenmeten.nl

### 3. Luchtmeetnet 

**Links:**
* https://www.luchtmeetnet.nl/informatie/download-data/open-data
* https://api-docs.luchtmeetnet.nl/

### [4. Hollandse Luchten Realtime tool](https://samenmeten.rivm.nl/hollandseluchten/)
Hiermee kun je data plotten en downloaden van individuele sensoren. 
De API lijkt me handiger.

### [5. GCN Tool](https://apps.rivm.nl/sla/gcn-tool/)
Meer data vanuit RIVM, niet per se downloadbaar of met een API?

## Links
* https://github.com/markkrijgsman/hollandseluchten