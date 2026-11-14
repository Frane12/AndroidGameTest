# DRNAS HALL3 + CF7 — završni STANDARD26 rezultat

Pokretanje: [GitHub Actions 43643413210](https://github.com/Frane12/AndroidGameTest/actions/runs/43643413210). Svi poslovi završili su uspješno. Testirani kod: `119d74530181b1a1b6bff2a40b0f17f929547990`.

24 originalne formule iz stvarnog Main Track skupa SAT Competition 2026, 12 obitelji, tri ponavljanja, četiri builda: ukupno 288 pokretanja. Limit 15 s i jedan logički CPU po solveru, 4 GiB adresnog prostora, 256 MiB po izlaznoj datoteci. Isti upareni ulazi, redoslijed ruku unaprijed nasumično određen.

## Glavni rezultat

Niži PAR2 je bolji. Srednji PAR2 računa se preko 72 pokretanja po buildu. Neriješeni, resursno ograničeni ili neprovjereni odgovori vrijede 30 s. Sve navedene riješene formule riješene su u sva tri ponavljanja.

| Build | Riješeno / 24 | SAT | UNSAT | PAR2 uz sve neovisne provjere | PAR2 samo MODEL/DRAT |
|---|---:|---:|---:|---:|---:|
| HALL3_ON | 4 | 1 | 3 | 25.481765 s | 29.215151 s |
| Kissat | 3 | 2 | 1 | 27.204849 s | 27.204849 s |
| CaDiCaL | 2 | 1 | 1 | 27.818338 s | 27.818338 s |
| CF7_OFF | 1 | 1 | 0 | 29.211436 s | 29.211436 s |

HALL3_ON ima 12,77% niži verificirani PAR2 od CF7_OFF, 6,33% od Kissata i 8,40% od CaDiCaLa. Tri dodatna UNSAT-a potvrđena su neovisnim provjerivačem strukturnih certifikata. Ti JSON certifikati nisu DRAT/LRAT, pa u zasebnom MODEL/DRAT poretku vodi Kissat.

## Tri strukturna pogotka

Medijani tri ponavljanja. E2E uključuje pokretanje, parsiranje, analizu/solver i neovisnu provjeru certifikata.

| ID | Obitelj | Kontradikcija | Solver | Solver + provjera |
|---|---|---|---:|---:|
| 1 | exam-scheduling | 81 > 80 | 0.253526 s | 1.413033 s |
| 18 | chnl | 51 > 50 | 0.054762 s | 0.274567 s |
| 19 | chnl | 31 > 30 | 0.089858 s | 0.415065 s |

Na sva tri pogotka Kissat je dosegnuo 15 s bez rješenja. CF7_OFF je dosegnuo limit datoteke dokaza od 256 MiB. CaDiCaL je na ID 1 i 18 dosegnuo isti limit dokaza, a na ID 19 vremenski limit. To nije tvrdnja da reference nikada ne mogu riješiti te formule.

Sva tri certifikata ponovno su izrađena iz istih originalnih CNF bajtova i neovisno provjerena i lokalno. `replayed_certificates/` čuva te ponovljene dokaze i SHA256 potvrde. Lokalna vremena nisu pomiješana s CI mjerenjima.

## Trošak provjere i ograničenja

Posebni E2E PAR2 uključuje provjeru u isti limit od 15 s. Zbrojevi: HALL3_ON 1839,956660 s; CF7_OFF 2103,367257 s; Kissat 2021,416830 s; CaDiCaL 2013,561666 s. Na ID 13 Kissatov DRAT provjerivač traje oko 69 s, zato ta formula ne ulazi u prihvaćene odgovore u E2E-15s tablici; ulazi u uobičajenu solver-time tablicu nakon uspješne provjere.

Srednje upareno poboljšanje HALL3_ON prema CF7_OFF je 3,729671 s po formuli. Bootstrap preko izvora daje 95% interval [-0,003715; 8,689598] s, koji uključuje nulu. Uzorak je malen, dobitak je koncentriran u tri strukturna slučaja i nije dokaz opće nadmoći. Cilj od najmanje 10% prednosti nad najboljom vanjskom referencom još nije dosegnut.

HALL3 je na SAT formuli ID 12 imao medijan 11,167414 s, CF7_OFF 11,074343 s, Kissat 2,425799 s. Na ID 13 reference su dokazale UNSAT, a oba DRNAS builda ostala su neriješena. Na ID 14 samo je Kissat pronašao provjeren SAT model. To ostaje prioritet za širi CDCL napredak.

Nema neispravnih SAT modela, odbačenih UNSAT dokaza ni proturječnih verificiranih odgovora u ovom pokretanju. Ishodi: 216 TIMEOUT, 42 RESOURCE_LIMIT, 15 SAT_VERIFIED i 15 UNSAT_VERIFIED. Neprovjereni odgovori nisu bodovani kao riješeni.

Prije benchmarka prošle su 71 integracijska provjera, 116 sintetičkih Hall2 kontrola (54 strukturna UNSAT, 34 DRAT UNSAT, 28 SAT), 18 ranijih Hall regresijskih/fuzz slučajeva i četiri provjere sučelja vanjskih solvera. Sintetički rezultati odvojeni su od natjecateljskih.

Izbor je napravljen po zamrznutom metapodatkovnom pravilu i veličini, bez mjerenja kandidata. Izbačene su poznate datoteke iz zabilježenog HALL2/CROSS100 skupa. Ovo nije potpuna revizija svih povijesnih grana i nije dokaz globalno neviđenog holdouta. Veće obitelji koje nisu stale u limit nisu zastupljene; detalji su u manifestu.

## Datoteke

- `summary.json`: završni CI obračun i usporedbe po formuli.
- `trials.jsonl`: svih 288 točnih redaka iz završenih CI poslova.
- `protocol.json`: hashovi binarnih datoteka, provjerivača i zamrznutog manifesta.
- `replayed_certificates/`: tri lokalno ponovljena strukturna dokaza i neovisne provjere.
- [Manifest i izvorni protokol](../../research/hall3/README.md).
- [Završni mali CI arhiv](https://github.com/Frane12/AndroidGameTest/actions/runs/43643413210/artifacts/14133188760).

Kod i rezultati ostaju u eksperimentalnoj grani; automatske promocije nema.
