# DRNAS X23G — binarni implikacijski GRAF umjesto brojanja klauzula

Zasebna eksperimentalna grana. X22, X23 i main ostaju netaknuti.

X23 mjeri gustoću binarnih klauzula i direktne duplikate. X23G prati
usmjerene implikacije i jače povezane komponente (SCC).

Za originalnu CNF X23G uzima četiri prozora do 64 KiB, s početka, iz
dva srednja područja i s kraja datoteke (ukupno najviše 256 KiB).
Za svaku originalnu binarnu klauzulu (a OR b) dodaje implikacijske
bridove (-a -> b) i (-b -> a). Nakon svakog prozora zapisuje presjek:
broj čvorova i bridova, SCC cikluse, signed alias x = +/-y,
moguće kontradikcije, duljinu stvarnih lanaca do 6 koraka,
doseg iz čvorova velikog izlaznog stupnja i razgranatost.

Šest usporednih konfiguracija:
1. race_original — originalna utrka Kissat + CaDiCaL.
2. race_quotient — X22 puni C++ signed-SCC reducer.
3. gate_strict — izvorna X23 stroga politika.
4. gate_liberal — izvorna X23 liberalna politika.
5. graph_scc — reducer samo kad uzorkovani graf sadrži dokazivu
   signed varijabilnu ekvivalenciju u SCC-u.
6. graph_frontier — reducer ako postoji takva ekvivalencija, ili ciklus
   uz put duljine barem 4, ili put dubine barem 5 s dosegom barem 20.

Uzorak je samo SIGNAL selektoru, nikad zamjena za dokaz.
C++ reducer i dalje koristi punu izvornu CNF i X22 neovisni Python
replayer prije pokretanja reducirane formule. Svaki SAT svjedok
provjerava se na izvornom SHA. UNSAT se ocjenjuje samo uz slaganje
izvornih Kissat/CaDiCaL referenci iz zamrznutog X22 izvještaja:
slaganje nije LRAT/FRAT certifikat.

Svi troškovi detekcije ulaze u E2E limit 15 s. Ako analiza prijeđe
meki limit 0,45 s ili graf premaši 85.000 bridova, politika se
suzdržava i prelazi na originalnu utrku. Upareni test:
24 originalne SHA formule, 2 ponavljanja, 6 strategija, 8 shardova,
ukupno 288 E2E mjerenja. Izvorni X21 holdout sada se ponavlja —
nije novi slijepi test. Bez automatske promocije.
