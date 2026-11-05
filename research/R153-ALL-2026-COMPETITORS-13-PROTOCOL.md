# DRNAS R153 — neslužbeni turnir protiv natjecatelja, identičnih 13 izvornika

## Značenje izraza "svi suparnici"
Svi javno objavljeni SAT Competition 2026 **Main** i **Main-AI** rezultati za točno 13 GBD-ID-ova prikazani su u posebnoj tablici `official_all_2026.csv/json`; uvjeti su onakvi kakvi su bili u službenom natjecanju i **nisu** na istom GitHub hardveru. Nije moguće reći da smo izveli *svaki* svjetski solver na GitHubu. U istom runneru na svih 13 originalnih CNF formula izvodimo šest stvarnih, verificiranih buildova:

- DRNAS R153 frozen GF(2) + certified units (`research/r153_exact_units_gf2.cpp`);
- DRNAS R28 unchanged (`experiments/drnas_v16/r28_exact_gf2.cpp`);
- pinani originalni Kissat 4.0.4;
- pinani originalni CaDiCaL 3.0.1;
- CryptoMiniSat iz Ubuntu 24.04 paketa (`cryptominisat5`, paket/binary SHA evidentirani);
- originalni submitted SAT Competition 2026 pobjednički `kissat-sc2024` iz potvrđenog `biere.tar.xz` izvornog arhiva i našeg uspješnog reproduciranog CI builda run `42105963889` (bin SHA i tar SHA moraju odgovarati).

## Frozen identitet izvora

Doslovno isti 13 originalnih SATCompetition2026 GBD formula, original SHA iz `r152-new-lightsout-frozen-originals-and-provenance` run `42102227483`, bez izmjena, izlaganja novim značajkama ili selekcije po brzini. R153 je na njima već razvijan/testiran i **ovo nije nova blind validacija**. Pri usporedbi s objavljenim svjetskim najboljima ne smije se koristiti sintagma "svjetski rekord".

## Protokol

- 6 buildova, 13 CNF, 2 ponavljanja svaki, 4 sharda, ukupno točno **156 pariranih izravnih mjerenja**.
- Wall-time limit 20 s po pokušaju, timeout PAR-2=40 s. Redoslijed modova deterministički pseudonasumičan po SHA i ponavljanju. Isti CPU unutar formule/sharda; runneri mogu varirati među shardovima.
- Svi potrebni binarni SHA, izvori i modeli su evidentirani. Ista originalna formula se šalje svakom suparniku.
- SAT model se provjerava na svim klauzulama izvornog CNF-a. R153 GF(2) UNSAT zaključci imaju neovisno ponovljenu provjeru izvornog XOR+unit podskupa. Ostali UNSAT zaključci nisu automatski nezavisno LRAT certificirani.
- Nema modifikacija stabilnih solvera ni formule. Nema automatske promocije.
- Završni audit: solved, timeouts, SAT, UNSAT tier, ukupni i po-slučaju PAR-2, median, formula wins/losses, regresije ≥2×, stratified bootstrap 95%, kompletni CSV.
- Odvojena službena tablica: svaki 2026 objavljeni solver s verificiranim statusom na ovih 13, i objavljeno vrijeme; sumirani historical PAR-2 (5000 s cap) samo u zasebnom listu. Ne smije se koristiti kao usporedba istog hardvera ili isto vremensko ograničenje.
- Svi runovi su neslužbeni, svaki rezultat se prikazuje, pa i ako R153 izgubi.

## Prije ovoga
- R153 dev audit: https://github.com/Frane12/AndroidGameTest/actions/runs/42104688630
- R153 odluke mikrotest: https://github.com/Frane12/AndroidGameTest/actions/runs/42105327238
- Službeno natjecanje: https://satcompetition.github.io/2026/downloads.html
- Izvorni R28 Full build 2026: https://github.com/Frane12/AndroidGameTest/actions/runs/42105963889

**Granica tumačenja:** usporedba sa svim poznatim rezultatima ≠ test svih svjetskih binarnih solvera na istoj mašini. Svjetske objavljene rezultatske brojke prikazuju se, ali bez reklamiranja nepostojećeg službenog rekorda.
