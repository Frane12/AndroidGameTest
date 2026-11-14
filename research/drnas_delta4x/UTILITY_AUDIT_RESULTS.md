# DRNAS DELTA4X — istraživanje cijene uvjetovanih ekvivalencija

Datum: 2026-11-14. Izdvojena grana: `experiment/drnas-delta4x-utility-audit-20261114`.

**CI:** https://github.com/Frane12/AndroidGameTest/actions/runs/43599098384 (sve 4 dijagnostičke podjele i sigurnosna provjera: PASS).

## Problem i hipoteza

Izvorni DELTA4X (zamrznuti SHA `bbc4943a123a8752625e8fa04a9359f1aca7f4158dd60a69b70f522c434e0ef6`) traži izvorno dokazive RUP rezolvente tipa `(-a OR g OR b)` uz originalnu obrnutu binarnu implikaciju `(a OR -b)`. Kad je `g` FALSE, dvije varijable moraju imati jednaku vrijednost. Izvedena klauzula ulazi u normalni CDCL, a zasebni promatrač alias-veza samo pamti aktivaciju i povrat.

U izvornom kodu `Delta4XEngine::trailChange` prelazi preko zapisa veza za dodjele, a `refresh` radi prilikom povratka. Na tim pozivima mogu nastati troškovi koje `DELTA4X_STATS.analysis_ms` ne uključuje.

## Metodologija

* Izvorne **SHA-zamrznute SAT2024 formule** ID8, ID19, ID28, ID38, na jednoj logičkoj CPU jezgri po serijski pokrenutom solveru.
* Četiri ruke: `X_ACTIVE` (izvorni zamrznuti DELTA4X), `X_OBSERVER_OFF` (izvedena inačica s uklonjena **samo dva promatračka poziva** — per-trail `trailChange` i per-backtrack `refresh`), `X_SHADOW` (bez X klauzula) i `D4_FIXED`.
* 3 ponavljanja × 4 ruke × 4 originalne formule = **48 pokušaja**. Limit 3 sekunde po pokušaju. Jednak CPU, isti izvorni CNF i SHA; izmjenjivan redoslijed ruku po zamrznutom seed-u.
* Izvorni binarni SHA potvrđen nakon ponovne izgradnje; referentni binarni SHA-ovi nisu izmijenjeni. Binarni SHA promatrača-bez-praćenja: `8ed910baed0e66e52b9e649c9f79537eb7d2cb807421f36bef0f20d21a86cac6`.
* Sintetičke kontrole `core`, `unsat`, `shifted_5005`: isti broj umetnutih klauzula i uzročnih CDCL dodjela, SAT modeli i UNSAT dokazi neovisno verificirani; izvorno-RUP pravilo pregledano.
* Sve četiri originalne formule ostale su UNKNOWN u 3 sekunde pod svim rukama. Broj konflikata mjera je **propusnosti pretrage**, ne broja ušteđenih konflikata ili ostvarenog ubrzanja do SAT/UNSAT rješenja.

## Rezultati: zbroj konflikata u tri ponavljanja (3 sekunde po ponavljanju)

| Formula | X_ACTIVE, promatrač UKLJ. | X_OBSERVER_OFF | X_SHADOW | Omjer OFF / ACTIVE | X klauzule po ponavljanju |
|---|---:|---:|---:|---:|---:|
| ID8, circuit-multiplier | 225.833 | 283.585 | 301.058 | **+25,6 %** | 24 |
| ID19, sted | 121.285 | 150.463 | 152.009 | **+24,1 %** | 19 |
| ID28, fermat | 66.136 | 71.782 | 71.573 | **+8,5 %** | 14 |
| ID38, dltm-twitter | 11.202 | 20.888 | 21.475 | **+86,5 %** | 53 |

## CDCL propagacije čiji je neposredni razlog X klauzula (zbroj tri ponavljanja)

| Formula | X_ACTIVE | X_OBSERVER_OFF |
|---|---:|---:|
| ID8 | 28.394 | 36.576 |
| ID19 | 9.466 | 11.977 |
| ID28 | 0 | 0 |
| ID38 | 15.699 | 37.423 |

Usporedbe su pri jednakom vremenskom limitu. Kada je promatrač isključen, solver stigne obraditi više pretrage i samim time može više puta iskoristiti iste klauzule. To nije isto što i toliko dodatnih jedinstvenih posljedica. Broj umetnutih klauzula bio je jednak između `X_ACTIVE` i `X_OBSERVER_OFF` na svakoj od četiri formule.

## Blokovski primjer: ID38, izvorna CNF

Originalni roditelji: `(-84 OR 1)` i `(-1073 OR 84 OR 86)`. Rezolucija na varijabli 84 daje novu originalno dokazivu klauzulu `(-1073 OR 1 OR 86)`. U originalu postoji i obrnuta implikacija `(-86 OR 1073)`.

Zato uvjet `x1=0` implicira `x86=x1073`. Izvedena klauzula skraćuje put zaključivanja: pod djelomičnom dodjelom `x1=0, x86=0` neposredno zaključuje `x1073=0` bez zasebne međukorak-klauzule preko `x84`. Ova posljedica je već logički sadržana u originalu — nije novi teorem.

*Na ID38 je originalni DELTA4 imao nula pripremljenih blokova; X otkriva rezolvente preko neovisnog indeksa kratkih originalnih klauzula.*

## Istraživački zaključak

U ovoj kontroliranoj ablacijskoj usporedbi **održavanje promatrača uvjetovanih veza objašnjava velik dio izgubljene računalne propusnosti** na sve četiri formule, osobito ID38. Na ID28 opaža se trošak čak i kad je broj stvarnih X-propagacija nula.

Ovo je dokaz računskog troška na odabranim retrospektivnim formulama, ali **nije dokaz ubrzanja vremena do rješenja**, generalizacije niti nove matematike. Naša ablacijska inačica još ostavlja jednokratni `refresh(values)` pri pohrani klauzule; mjeri se dominantan trošak trail/backtrack skeniranja, ne apsolutno sav observer trošak. Odluke i redoslijed pretraživanja mogu se razlikovati zbog vremenskih uvjeta; zato se uspoređuju stope obrade, ne tvrdi se da je putanja identična.

**Sljedeći znanstveni korak:** profilirati izolirano `trailChange/refresh`, testirati jeftinu indeksiranu registraciju `guard -> aliases` ili ukloniti promatrač u produkcijskom modu ako nije dio CDCL semantike. Zatim na novim SHA-disjunktnim formulama i većem vremenskom limitu neovisno provjeriti stvarno rješavanje i PAR2, bez promocije na `main`.

## Evidencija

Workflow: https://github.com/Frane12/AndroidGameTest/actions/runs/43599098384

Datoteke pod `research/drnas_delta4x/utility_audit.py`, `.github/workflows/drnas-delta4x-utility-audit.yml`, odgovarajući artefakti `delta4x-utility-source-8/19/28/38` i `delta4x-utility-proof-preflight`. Samo eksperimentalna grana; izvorni `main` i stari DELTA4X nisu mijenjani.
