# DRNAS X5: konfliktno učenje i upravljanje memorijom

Eksperimentalna grana: `experiment/drnas-x5-clause-engine-20261113`.
Zamrznuta polazna grana: `frozen/drnas-x47-core-learned-20261113`,
commit `1670a8fd3e56ae13f0c527240e30d1037e7bfa8b`.
`main` i stari izvori ostaju netaknuti. Nema dokazanog univerzalnog pobjednika;
CORE je stabilna kontrola, X46_LEARNED_8 najbolji kandidat na nekim skupovima.

## Zašto promjena jezgre

Potvrđeni prethodni CI nalazi:

| Test | CORE PAR2 s | X46_LEARNED_8 PAR2 s | Tumačenje |
|---|---:|---:|---|
| FAST5, 24 izvora / 48 pokušaja po ruci | 62.856183 | 62.157220 | 1.11% niže, interval uključuje nulu |
| HARD4, 64 izvora / 128 pokušaja | 870.971241 | 869.968321 | 0.12% niže, širok interval |
| PHP5, 64 izvora / 128 pokušaja | 16.676694 | 17.067739 | 2.34% lošije |

Izvori: [FAST5](https://github.com/Frane12/AndroidGameTest/actions/runs/43365276251),
[HARD4](https://github.com/Frane12/AndroidGameTest/actions/runs/43364679494),
[PHP5](https://github.com/Frane12/AndroidGameTest/actions/runs/43366219413).
[GATE-R3](https://github.com/Frane12/AndroidGameTest/actions/runs/43364794762)
ima CORE 127.6344026 s, R2 125.4919595 s, R3 133.3610663 s;
ni tamo nije prošao kriterij promocije. Veći model ili manje sondiranja
nisu sami po sebi dokaz boljeg rješavanja.

## Implementacija

- Rekurzivna minimizacija 1-UIP naučenih klauzula preko grafa razloga.
  Brisanje literala dopušta se samo kad razlog završava u korijenskim
  činjenicama ili drugim literalima naučene klauzule. Limit 4000 posjeta
  i dubina 128: iscrpljen limit zadržava literal.
- Ograničavanje zastarjelih zapisa u redu prioriteta; brza deterministička
  selekcija varijable bez privremenog vektora i ponovnog umetanja.
- Fizičko uklanjanje mrtvih klauzula uz preslikavanje razloga, jedinica,
  binarnih implikacija i watch-lista. Zaključani razlog se nikada ne briše.
- Izborni slojevi zadržavanja prema LBD-u, nedavnoj uporabi i opadajućoj
  aktivnosti. Trajno zaštićen LBD <= 2; dulja zaštita za LBD <= 6;
  briše se trećina kandidata. **Ovo nije zadano uključeno:** mali razvojni
  pokus nije potvrdio korisnikovu hipotezu da je manje brisanja uvijek bolje.
- Izborni restart prema kratkom i dugom prosjeku LBD-a; nije zadan jer
  validacija nije potvrdila korist.
- DRAT izlaz i provjera izvornog SAT modela. Zamrznuta kontrola dobiva
  isključivo zapis dokaza kroz reproducibilni generator, bez promjene
  pretraživanja. Test provjerava podudaranje odluka, konflikata i propagacija.
- Nema prenošenja logičkih klauzula među različitim CNF-ovima, skrivenog
  portfelja ni podataka o obitelji/rezultatu u odabiru odluke.

Ovo je primjena poznatih CDCL postupaka, ne tvrdnja o novom matematičkom
algoritmu ili P=NP. Relevantni izvori: [Glucose i glue klauzule](https://www.labri.fr/perso/lsimon/research/glucose/),
[Learn to Unlearn, SAT 2025](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2025.14),
[minimizacija naučenih klauzula](https://home.mis.u-picardie.fr/~cli/ijcai17.pdf).

## Lokalna mjerenja i izbor kandidata

Razvoj: 36 novih izvora, 6 obitelji, 2 ponavljanja, limit 0.7 s.
Odabrana varijanta imala je PAR2 **5.694991 s / 70 od 72**, CORE
**10.407692 s / 66 od 72**, X46 **9.926970 s / 67 od 72**.
U `development_*` podacima odabrana varijanta nosi naziv `X5_NO_RETAIN`;
u konačnom izvoru to je zadani `X5`. Sačuvan je točan razvojni C++ snapshot.
Razvojni rezultat služi izboru, nije dokaz generalizacije.

Sljedeća validacija: 48 novih izvora, 6 obitelji, 2 ponavljanja, limit 1.5 s:

| Varijanta | Riješeno / 96 | Verificirani PAR2 s |
|---|---:|---:|
| CORE | 80 | 53.206631 |
| X46_LEARNED | 80 | 52.988943 |
| X5 | 82 | 47.179593 |
| X5_NO_MIN | 84 | 43.872683 |
| X5_RETAIN | 80 | 51.694952 |
| X5_RESTART | 80 | 53.375615 |

X5: **11.33% niži PAR2 / 1.128x** od CORE-a; 95% interval po izvornoj
formuli **[-3.75%, +36.47%]**. U odnosu na X46: 10.96% niži PAR2,
interval [-3.86%, +35.97%]. Dakle, još nema statističke potvrde.
Varijanta bez minimizacije je u ovoj validaciji bolja od punog X5;
minimizacija nije univerzalna korist. Ostaje zasebna ruka u slijepoj provjeri.
RAM su maksimumi dovršenih procesa; ubijeni procesi nemaju RSS uzorak,
pa se iz tih brojeva ne smije tvrditi ukupno smanjenje vršne memorije.

Točnost: 1128 pokretanja, 676 neovisnih UNSAT provjera, male formule s
iscrpnim oracleom, izvorni SAT modeli, stvarno aktivirana minimizacija i GC,
namjerno pogrešan dokaz odbijen. Konačni test: `correctness.json`.

## Unaprijed zaključana CI provjera

- Sintetički holdout: 96 jedinstvenih SHA, 6 obitelji, offset 6100000,
  9 ruku, 2 ponavljanja = **1728 pokretanja**.
- Originalni SAT2024: 12 različitih SHA/obitelji odabranih prema veličini,
  6 ruku, 2 ponavljanja = **144 pokretanja**. Retrospektivno, ne globalno slijepo.
- Zajedno **1872 benchmark pokretanja**, plus testovi ispravnosti i sučelja.
- Jedan logički CPU, ruke serijske, nasumičan redoslijed, cijeli E2E limit 5 s
  uključuje pokretanje, parsiranje, izlaz, dokaz i provjeru.
- Kissat 4.0.4 i CaDiCaL 3.0.1 vezani uz commit; CryptoMiniSat paket Ubuntu
  24.04 (verzija i hash zapisani), `--threads=1`.
- DRAT checker vezan uz commit; CMS FRAT se elaborira i neovisno provjerava
  kao LRAT pomoću vezane verzije FRAT-rs. Neprovjeren UNSAT i prekoračenje
  ukupnog limita dobivaju 2*cap. Poznati izlaz drat-trim za trivijalni UNSAT
  vraća kod 1 uz `c trivial UNSAT` i `s VERIFIED`; prihvaća se samo taj slučaj.
- Repeticije nisu nezavisni izvori. Bootstrap po izvornom SHA, kategorije i
  regresije odvojeno. Nepotpuni parovi ili shardovi ruše izvještaj.
- Promocija zahtijeva >=10% niži PAR2 od obiju nativnih kontrola, donji
  interval >0 i bez gubitka riješenih pokušaja po obitelji u oba skupa.
  Pobjeda nad vanjskim solverima ocjenjuje se odvojeno. Nema automatskog mergea.

## Reprodukcija

```sh
mkdir -p build
python3 research/drnas_x5_prepare.py
g++ -std=c++20 -O3 src/drnas_x41.cpp -o build/frozen-core
g++ -std=c++20 -O3 build/frozen-proof.cpp -o build/frozen-proof
g++ -std=c++20 -O3 src/drnas_x5.cpp -o build/drnas-x5
gcc -O2 research/drnas_x5_time.c -o build/timed
# Potrebni proof checkeri i reference: research/drnas_x5_build_refs.sh
python3 tests/test_x5.py
python3 research/drnas_x5_bench.py --out own_run --count 48 --offset 7000000 --cap 5 --repeats 2
```

`src/drnas_x41.cpp` i modeli zaštićeni su SHA256 provjerom.
Razvojni i validacijski manifesti, sirovi rezultati i intervali ostaju uz kod.

Lokalni manifesti imaju bazni SHA256 561c9854… jer je lokalna kopija imala
jedan završni newline više. Pohranjena kontrola i CI koriste točne originalne
bajtove (805c298e…); C++ sadržaj i ponašanje su isti.
