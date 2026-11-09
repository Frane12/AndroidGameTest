# DRNAS X22 — asinkroni C++ reducer + Kissat + CaDiCaL

Eksperimentalna grana, bez izmjena stabilnog maina ili X21 referenci.

## Hipoteza

Kissat započinje pretraživanje na logičkom CPU-u A i ne gubi naučene
klauzule. Na CPU-u B zaseban C++ proces iz ORIGINALNIH binarnih klauzula
gradi graf implikacija, pronalazi SCC i izvodi samo dokazive zamjene
pozitivnih ili negiranih varijabli. Ne koristi nagađanje XOR-a niti rezultate
solvera. Redukcija također uklanja tautologije, ponovljene klauzule i
ponovljene literale te stavlja kraće klauzule ranije.

Drugi Python replayer *neovisno o C++ logici* gradi originalni graf i
provjerava oba implikacijska smjera svake zamjene. Tek tada se CaDiCaL
pokreće na reduciranoj formuli; ako Kissat završi ranije, radnik se gasi.
Svaki prihvaćeni SAT svjedok rekonstruira se u originalne varijable i
provjerava nad punom izvornom CNF formulom.

## Šest usporednih konfiguracija

- kissat1: izvorni Kissat, jedno logičko CPU
- cadical1: izvorni CaDiCaL, jedno logičko CPU
- race_original: Kissat + CaDiCaL odmah na dva logička CPU-a
- race_shadow: C++ reducer se izvrši, ali CaDiCaL dobije original
- race_clean: CaDiCaL dobije samo čistu i preuređenu formulu bez aliasa
- race_quotient: CaDiCaL dobije dokazani signed-SCC kvocijent

Stoga je usporedba race_quotient vs race_original ključna za odvajanje
koristi matematičke redukcije od koristi obične paralelne utrke.
race_shadow mjeri cijenu izračuna, a race_clean izolira korist čišćenja
i redoslijeda od spajanja varijabli.

## Kontrole i ograničenja

24 formule su preuzete iz ranije dovršenog X21 holdouta:
one **više nisu neviđene** i X22 ne smije biti proglašen slijepim testom.
Dvije repeticije x 6 konfiguracija x 24 SHA = 288 E2E mjerenja,
8 shardova, 15 s wall cap, najviše dva afinitetom ograničena logička CPU-a.
Bilježe se stvarno E2E vrijeme, ukupni CPU djece, PAR2, potpunost i
izvorni SHA. Ne postoji automatsko promoviranje.

SAT se prihvaća samo uz provjeru modela na originalu. UNSAT se
prihvaća u aggregate PAR2 samo kad su i izvorni Kissat i izvorni
CaDiCaL za isti SHA dali UNSAT, i to je **slaganje dvaju solvera,
ne neovisni LRAT/FRAT dokaz**. Kvaliteta redukcije sama po sebi ne
potvrđuje UNSAT certifikat. Rezultati iz nerevidiranih shardova
ne smiju se prikazivati kao konačan dobitak.

CI prije benchmarka kompilira C++ te testira stotine malih
SAT/UNSAT primjera iscrpnim enumeriranjem i neovisnim replayem.
