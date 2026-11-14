# DRNAS: samo ranije riješene stvarne nelinearne formule

14. studenoga 2026. — lokalno završen eksperiment, jedan logički CPU.

## Strogi odabir

Devet izvornih SAT Competition 2024 Simon CNF-ova (r16–r24), ID-ovi
2, 8, 14, 18, 22, 26, 29, 32 i 35 iz REAL36. Svaki je prethodno dvaput
verificirano riješen DRNAS OFF referencom u runu 43587320318, ispod 5 s.
Svi tadašnji baseline timeouti i formule bez potpunog AND certifikata su isključeni.
SHA-256 i prethodna mjerenja nalaze se u `cohort_summary.json`.

Neovisno je potvrđeno 512, 544, 576, 608, 640, 672, 704, 736 i 768
potpunih potpisanih AND definicija. Tri originalne klauzule
`(z or -a or -b), (-z or a), (-z or b)` točno kodiraju `z=a*b`.
Svaka je provjerena iscrpnom lokalnom tablicom istinitosti. Ovo dokazuje
lokalne kvadratne članove, ne globalnu nereducibilnost ni novu matematiku.

## Rezultat

20 ponavljanja × 9 originala × 5 režima = **900/900 SAT_VERIFIED**, bez timeouta.
Redoslijed je deterministički promiješan; prije mjerenja provedeno je još
45 verificiranih zagrijavanja. BASE, INPLACE i DELTA4X koriste isti novi izvršni
program, iste proof opcije i isti CPU. Svaki model provjeren je na izvornom CNF-u.

| Režim | Zbroj medijana za 9 izvora | Promjena vremena prema BASE |
|---|---:|---:|
| BASE, matematika isključena | 62.153 ms | — |
| INPLACE, nova priprema | 53.267 ms | −14.30% |
| DELTA4X, aktivna matematika | 83.192 ms | +33.85% |
| Kissat | 46.275 ms | −25.55% |
| CaDiCaL | 64.040 ms | +3.04% |

Vrijeme obuhvaća pokretanje procesa, čitanje, prepoznavanje ako je uključeno,
rješavanje, proof emisiju i ispis modela. Neovisna provjera izvornog CNF-a
mjeri se odvojeno. S uključenom provjerom modela INPLACE smanjuje zbroj medijana
za **7.78%**. Suma svih verificiranih PAR2 vremena smanjena je za **11.49%**.
INPLACE je još **15.11% sporiji od Kissata** po zbroju medijana.

INPLACE koristi normalizaciju klauzula u postojećem vektoru, unaprijed rezervira
spremnik klauzula i mali ulazni vektor. Time uklanja kopiranje i ponavljane
alokacije, bez mijenjanja logike. Svih 180 uspoređenih pokušaja BASE/INPLACE
ima identične brojeve odluka, konflikata, propagacija, naučenih klauzula i restarta.
Svaki ima 32 odluke i 0 konflikata. Medijan pripreme pao je s 3.258 na 2.269 ms;
medijan pretrage ostao je oko 1.15 ms.

Opisni bootstrap po devet izvora daje raspon 12.02–16.65% za smanjenje vremena.
Izvori pripadaju jednoj povezanoj Simon obitelji: ovo nije slijepi test,
dokaz dobitka na drugim obiteljima ili razlog za promociju u main.
Ranija razvojna verzija samo s normalizacijom i rezervacijom spremnika dala je
6.37%; nakon dodavanja rezervacije ulaznog vektora cijeli test ponovljen je.

## Odbačen matematički pokušaj

Prioritet odluka prema ulazima potpunih AND definicija nije pomogao.
Već na `simon-r16-1` promijenio je 32 odluke / 0 konflikata u 66,172 odluke /
56,968 konflikata i UNKNOWN na 4.93 s. Istraživanje tog režima je odmah
zaustavljeno; nije izbačen iz povijesti niti proglašen uspjehom.
Detalji su u `rejected_input_prior.json`. Ta odbijena pilot-varijanta nije
uključena u broj 900 završnih pokušaja. `inputs` i `both` ostaju eksplicitne
istraživačke opcije; nisu odabrana konfiguracija i ne koriste se u završnom testu.

Zaključak za ovaj skup: sama prisutnost kvadratnog člana ne opravdava mijenjanje
dobrog CDCL redoslijeda. Trenutni dobitak je inženjerski; dodatno algebraičko
ubrzanje nije potvrđeno.

## Provjera i ponavljanje

68 malih slučajeva × 4 konfiguracije: 272/272 odgovara iscrpnom oracleu,
60 SAT modela i 212 UNSAT DRAT dokaza neovisno provjereno. Uključeni su duplikati,
tautologije i prazne klauzule. Sintetički slučajevi koriste se samo za provjeru
ispravnosti; nisu dio istraživanja brzine.

Izvor je zamrznuti DELTA4X commit `1bf23bd7a98521d5486d706c2b012055847e9bf4`.
Generirani početni C++ ima provjeren SHA-256 u `build.py`.
Finalni testirani binarni SHA-256: `7c11ef877f18fea0e6f84e2445aa1bb4cc295245dcabfd81477b7528fc3cd81a`.
Potpuni metapodaci su u `local_report.json`, a svih 900 redaka u
`local_trials.jsonl.gz`. Rezultat je lokalno mjeren; CI replay nije još pokrenut.

Workflow `.github/workflows/drnas-nonlinear-solved.yml` omogućuje ručno
ponavljanje na GitHubu s izvornim artefaktima i istim strogo odabranim skupom.
Nema automatskog širokog benchmarka, APK builda ili promjene maina.

Nakon vraćanja izvora i referenci prema workflowu:

```sh
python3 research/drnas_delta4x/build.py
python3 research/drnas_nl_solved/build.py
python3 research/drnas_nl_solved/validate.py
python3 research/drnas_nl_solved/bench.py --history history/delta3_final/trials.json --reps 20 --out nl_solved_ci
```

Odabrani režim: `build/drnas-nl-solved INPUT.cnf --mode core --x5-no-minimize
--coop4 off --coop5 off --nl-focus inplace --proof OUTPUT.drat --stats`.
Optimizacija nema lookup prema nazivu, SHA-u, očekivanom ishodu ili prethodnom modelu.

## Dodatna provjera izvan Simona

[Rezultati na pet lakših i srednje teških stvarnih formula](MEDIUM_RESULTS.md): 200/200 verificirano, bez potvrđenog ukupnog ubrzanja na tri dulje formule.
