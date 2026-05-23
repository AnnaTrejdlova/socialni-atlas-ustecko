# Prediktivní Sociální Atlas Ústeckého kraje

Tato webová aplikace představuje funkční prototyp **Rozhodovací podpory pro plánování sociálních služeb** v Ústeckém kraji. Kombinuje historická demografická data s prediktivním modelováním budoucích potřeb a socioekonomickými stresovými indikátory pro identifikaci ohrožených oblastí (tzv. "Bílých míst").

---

## 🏛️ Hlavní Funkce

1. **Sociální Atlas (Současnost)**:
   - Interaktivní kartografické zobrazení 16 obcí s rozšířenou působností (ORP) v Ústeckém kraji.
   - Vizualizace socioekonomických vrstev: *míra nezaměstnanosti*, *podíl obyvatel v exekuci*, *poměr sociálně vyloučených lokalit*, *kriminalita* a *příjemci příspěvku na bydlení*.
   - Zobrazení poskytovatelů sociálních služeb (pobytová zařízení, terénní péče, azylové domy) s detaily o kapacitě a využití.

2. **Prediktivní Model (Projekce 2026–2035)**:
   - Časový jezdec (Timeline slider) pro modelování stavu v letech 2026 až 2035.
   - Dynamické sledování **kapacitního deficitu pobytových lůžek** na základě trendů stárnutí nejohroženější skupiny seniorů (75+ let).
   - Nastavitelný práh kritického deficitu (např. 20 %) pro včasné varování (vizuální zčervenání ORP na mapě).
   - Výpočet a hodnocení **Indexu Bílých míst (White Spot Index - WSI)** pro prioritizaci krajských dotací.

3. **Exekutivní Analýza a Exporty**:
   - Automaticky generovaná zpráva s hodnocením rizik (Kritické / Střední / Nízké) pro vybrané území.
   - Možnost stažení surových datových sad ve formátech CSV (demografické řady, registr služeb) a JSON (výsledky predikcí).

---

## 🛠️ Použitá Technologie

- **Frontend**: Streamlit s prémiovou dark-theme šablonou a glassmorfismem (`frontend/style.css`, `frontend/app.py`).
- **Vizualizace**: Plotly (grafy) a Folium / Leaflet (interaktivní mapy s tooltipy a napojením na st_folium).
- **Backend API**: FastAPI s CORS a datovým modelem (`backend/api.py`).
- **Projekce a Analýzy**: NumPy a Pandas (`backend/forecasting.py`).

---

## 🚀 Jak aplikaci spustit

Aplikace vyžaduje nainstalovaný Python 3.11 nebo novější a nástroj pro správu závislostí `uv`.

### 1. Příprava prostředí a instalace
Pokud ještě nemáte nainstalované závislosti, inicializujte prostředí pomocí:
```bash
uv sync
```

### 2. Spuštění obou serverů najednou
V kořenovém adresáři projektu je připraven spouštěcí skript, který spustí jak **FastAPI backend** (port 8000), tak **Streamlit dashboard** (port 8501):
```bash
.venv\Scripts\python.exe -I run_app.py
```
*(Skript spouští procesy v izolovaném módu `-I`, což zabraňuje případným konfliktům s jinými instalacemi Pythonu na vašem systému).*

Následně otevřete prohlížeč na adrese:
👉 **[http://localhost:8501](http://localhost:8501)**

---

## 📊 Metodologie Predikce

### 1. Demografický model
Budoucí vývoj populace v jednotlivých ORP je predikován metodou **lineární regrese** (nejmenších čtverců) na základě historického vývoje z let 2018–2025:
- Zohledňuje se celková populace, skupina 65+, skupina 75+ a migrační saldo.
- Model předpokládá zrychlené stárnutí populace u sociálně zatížených regionů v důsledku odchodu mladší produktivní síly.

### 2. Kapacitní deficit
Deficit vyjadřuje přetlak poptávky nad stávající kapacitou pobytových zařízení (domovů pro seniory):
- Poptávka v cílovém roce se počítá jako procentuální podíl z forecasted populace 75+.
- U ORP bez jakéhokoliv stacionárního zařízení (např. Podbořany) je deficit automaticky roven 100 % (při existenci poptávky).

### 3. White Spot Index (WSI)
Vzorec pro výpočet Indexu Bílých míst (vyšší číslo značí naléhavější potřebu intervence):
$$\text{WSI} = \frac{\text{Socioekonomický Stres} \times \text{Tempo Růstu Populace 75+} \times 100}{\text{Celková Kapacita Služeb} + 10}$$

---
*Vytvořeno pro hackathon 2026 jako nástroj pro modernizaci veřejné správy v Ústeckém kraji.*
