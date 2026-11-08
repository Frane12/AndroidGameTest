# DRNAS SAT — kumulativna baza i istraživački nalaz
Datum: 8. studenoga 2026. | Grana: experiment/drnas-v1531-analytics-sqlite-20261101
Status: auditiran, bez promjene V15.3.1 i bez automatske promocije eksperimenata.

## 1. Što je stvarno ažurirano

Povijesna V15.3.1 SQLite ostaje netaknuta: 231 skup, 2.979 formula,
53.330 mjerenja. Nove rezultate spremili smo u pridruženi, SHA-256
provjereni MRE sloj:
research/sat-analytics-data/current/mre-evidence/mre_evidence.sqlite.gz

Novi audit obuhvaća **6 benchmark serija, 1.624 stvarna SAT/UNSAT pokušaja,
40 različitih originalnih formula (SHA-256), 64 članstva formula po
serijama, 1.420 uparenih usporedbi i 44 zapisa o izvornim artefaktima**.
Jedna formula u dva runa ostaje jedan originalni SHA i dvije različite
serije pokušaja. Time se ne napuhuje broj neviđenih formula.

Dokazi: GitHub Actions runovi
- MRE10 development (640): https://github.com/Frane12/AndroidGameTest/actions/runs/42509505558
- MRE10 identical-source repeat (640): https://github.com/Frane12/AndroidGameTest/actions/runs/42513793922
- MRE10b new-to-tracked official SAT23–25 (144): https://github.com/Frane12/AndroidGameTest/actions/runs/42511332725
- MRE6g (60): sirovi shardovi https://github.com/Frane12/AndroidGameTest/actions/runs/42505145407
  i završni ispravljeni audit https://github.com/Frane12/AndroidGameTest/actions/runs/42506460983
- MRE6h (60): https://github.com/Frane12/AndroidGameTest/actions/runs/42507215971
- MRE6i (80): https://github.com/Frane12/AndroidGameTest/actions/runs/42509063941
- Novi potpuni ingest audit: https://github.com/Frane12/AndroidGameTest/actions/runs/42515652015

Svaki pokušaj ima run SHA, originalni CNF SHA, seed, način rada, puni
wall-time i PAR-2, originalni provjereni SAT model ili jasno označeno
UNSAT slaganje s referencom (NE nezavisni LRAT dokaz), native CDCL
statistiku kada je prisutna, strukturalni gate i SHA sirovog retka.
Benchmark audit rezultati neovisno su uspoređeni sa svim sirovim
shardovima. Stare SQLite tablice nisu pisane.

## 2. PAR-2 rezultati: ubrzanje i regresije

Uspoređivati smijemo samo metode na istoj formuli, seedom i limitu,
NE PAR-2 zbrojeve različitih benchmark skupova. Omjer = baseline/DRNAS;
iznad 1× znači brže.

| Serija | Limit | Referentni PAR-2 | DRNAS PAR-2 | Riješeno referenca → DRNAS | Faktor |
|---|---:|---:|---:|---:|---:|
| MRE10 poznatih 16 CNF | 8 s | CMS 211,756782 s | C++ Joint 168,473602 s | 56/64 → 58/64 | **1,256914×** |
| MRE10 identično ponavljanje | 8 s | CMS 196,430859 s | C++ Joint 162,528832 s | 57/64 → 58/64 | **1,208591×** |
| MRE10b novih 12 CNF | 15 s | CMS 415,178377 s | C++ Joint 470,811893 s | 26/36 → 24/36 | **0,881835×** |
| MRE10b samo Clean | 15 s | CMS 415,178377 s | C++ Clean 426,287736 s | 26/36 → 26/36 | **0,973939×** |
| MRE6g official+known | 35 s | CMS+XOR 243,410476 s | SCC+GF2 245,178852 s | 10/12 → 10/12 | 0,992787× |
| MRE6h official+known | 35 s | CMS+XOR 287,428032 s | fast GF2 no-XOR 287,492381 s | 9/12 → 9/12 | 0,999776× |
| MRE6i official+synthetic+known | 35 s | CMS+XOR 332,860886 s | gated GF2 no-XOR 333,328952 s | 12/16 → 12/16 | 0,998596× |

MRE10 development dobitak doista se ponovno pojavio na **istim**
originalnim formulama, ali se **nije prenio na druge službene
originalne formule u MRE10b**. Nova serija pokazuje povećanje PAR-2
za 55,633516 s (13,40% više od CMS-a) i dva dodatna solved→timeout
regresivna pokušaja za Joint, bez ijednog novog riješenog pokušaja
prema CMS-u. Clean je na jednom seedu dobio dodatni solve, ali
izgubio drugi solve na zasebnom originalu; ukupno PAR-2 je lošiji.

Poznata SAT2025 formula 695d8f6a2ee6e89e5a4f5d94abc3aca6
opet ima velik dobitak kad se ukloni 560 redundantnih klauzula i
**nula varijabli**. Na drugoj, ranije korištenoj SAT2023 formuli
fdfcd52a21824b7181d66672f283ba04 isti dokazni mehanizam
opet spaja 1.318 varijabli i uklanja 7.361 klauzulu.
Ali SAT2024 be6411f4784a3c879886dda807cdc607 pokazuje
suprotan učinak: **C++ Clean 3/3 riješeno, CMS 2/3, Joint 1/3**.
Matematički manja formula nije zajamčeno brži CDCL.

## 3. Dodatni auditirani eksperimenti (katalog, NISU uključeni kao sirovi retci novog 1.624 sloja)

**MRE8 ABCX**: 512 pokušaja, već korištene formule;
Python C_joint PAR-2 175,707276 s vs native 203,552960 s,
58/64 vs 57/64; 1,158478× (razvojni signal).
Run: https://github.com/Frane12/AndroidGameTest/actions/runs/42506577511

**MRE8 native**: 512 pokušaja, 16 ranije korištenih originala,
N 236,648154 s, B cleanup 234,475757 s (1,009265×), C
234,511653 s (1,009110×), svi 54/64 riješeni; slaba
prenosivost koristi na ovom drukčije implementiranom testu.
Run: https://github.com/Frane12/AndroidGameTest/actions/runs/42507588566

**MRE11b source-selected 2021–23**: 8 ranije neprijavljenih
službenih originala, 128 pokušaja, limit 35 s.
CMS C++ native 13/16, PAR-2 319,895889 s. C++ Joint 14/16,
226,620410 s (1,411593× vs CMS); C++ Clean 14/16, 233,760024 s.
Ali CaDiCaL 16/16, 90,752491 s: Joint je 2,497× sporiji
od CaDiCaL-a na istome skupu. Kissat 14/16, 207,035953 s.
To je ograničen signal prenosivosti prema CMS-u, ali NE prema
jačim referentnim rješavačima.
Run: https://github.com/Frane12/AndroidGameTest/actions/runs/42511069503

**MRE11 official2026 8s**: 7 formula, 5 nativnih metoda, četiri
seeda: svih 140 pokušaja timeout, za svaku metodu 0/28
riješenih i PAR-2 448 s. To nije dokaz jednakosti algoritama,
nego nedovoljno informativan limit.
Run: https://github.com/Frane12/AndroidGameTest/actions/runs/42513542283

**MRE11-L35** u vrijeme ovog izvještaja još se izvršava,
te NEMA auditaran konačni PAR-2; stoga nije uvezen.
Run: https://github.com/Frane12/AndroidGameTest/actions/runs/42514613031

## 4. Cjelokupna znanstvena ocjena

Što je potvrđeno:
1. Certificirane ekvivalencije i sigurno uklanjanje redundantnih CNF
   klauzula mogu proizvesti **stvarna end-to-end ubrzanja**, uz
   rekonstrukciju i provjeru SAT modela na originalnoj formuli.
2. Izvorni MRE10 rezultat ponavlja se na istim 16 formula.
3. Stvarni dobitak **jako ovisi o strukturi formule, seedeu,
   reprezentaciji, rasporedu klauzula i CDCL heuristikama**.
4. MRE6h/6i smanjili su trošak GF(2) dokazivanja, ali na četiri
   novije stvarne SAT2026 formule nisu primijenili korisnu
   dokazanu eliminaciju; pet spajanja na lakom sintetskom XOR-u
   nisu nadoknadila CPU trošak.
5. Bez neovisnih UNSAT LRAT dokaza sve UNSAT tvrdnje treba
   označiti kao referentno/cross-solver slaganje.

Što NIJE potvrđeno:
- Opće ubrzanje na izvornim službenim SAT formulama.
- Pobjeda nad Kissatom ili CaDiCaL-om po PAR-2 na nezavisnom
  reprezentativnom skupu.
- Svjetski rekord, produkcijska spremnost ili robustna prednost
  na tvrdoj kategoriji official2026.
- Neovisnost svih formula od kompletne povijesti projekta,
  jer povijesni izvorni registri nisu iscrpni.

## 5. Prioritet za novo istraživanje

**MRE12 — selektivna, konzervativna strukturna predobrada.**

Zadržati V15.3.1, R28, MRE10 kao netaknute frozen reference.
Model/gate smije vidjeti samo jeftine original-CNF značajke:
udio redundancija (dup/taut), broj i gustoću dokazivih
ekvivalencija, lokalnu strukturu binarnih implikacija i
procijenjenu cijenu prepisivanja. Uključivati **Clean**, **Joint**
ili **Original** samo kada je očekivani puni CPU/PAR-2 dobitak
veći od cijene analize. Posebno učiti iz regresije be6411f...
kao negativnog razvoja, nikako kao birani holdout.

Najprije zaključati selektor i source-SHA train/test podjelu,
zatim odvojeno auditirati nove SAT/UNSAT realne formule sa 4–5
seedova i limitima prilagođenima rješivosti (15/35/90 s),
uključujući iste CMS/Kissat/CaDiCaL kontrole. Zadržati
nepromijenjene timeoutove u PAR-2, čuvati originalne SAT modele,
proof-tier i per-source regresije.

**Moj zaključak**: najveći potencijal više nije u "što više
eliminiranih varijabli" nego u unaprijed predviđenoj
**vrijednosti promjene reprezentacije za stvarnu CDCL pretragu**.
Matematički ispravna redukcija može ubrzati i jako usporiti.
Tu razliku treba objasniti i pouzdano prepoznati prije
eventualne promocije u solver.

## 6. Primjer povezivanja SQLite dokaza

Povijesnu bazu otvoriti bez pisanja, a odvojeni novi sloj
ATTACH-ati kao SQLite mre. U mre postoje:
mre_runs, original_sources, run_original_sources, mre_attempts,
mre_paired i artifact_lineage. Ključ pojedinog pokušaja:
(source_run, original_sha256, mode, repetition).
Formula se deduplicira po original_sha256 neovisno o runu.
