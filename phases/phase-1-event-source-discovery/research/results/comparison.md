# Approach comparison vs Wikipedia Current Events

Answer key: 38 entries in window (2026-11-02, 2026-11-03, 2026-11-04); matching allows ±1 day (61 entries).

P@k = share of top-k stories matching any entry. R@50 = share of window entries matched by a top-50 story. dup@20 = matched top-20 stories that repeat an already-matched thread (fragmentation). threads@20 = distinct threads hit in top 20.

## matching = strict (default)

| approach | stories | P@10 | P@20 | P@50 | R@50 | dup@20 | threads@20 |
|---|---|---|---|---|---|---|---|
| a_mention_graph | 150 | 0.80 | 0.75 | 0.68 | 0.21 | 12 | 3 |
| b_structured_keys | 150 | 0.60 | 0.65 | 0.58 | 0.29 | 6 | 7 |
| baseline_raw_events | 100 | 1.00 | 0.80 | 0.70 | 0.16 | 14 | 2 |
| c_article_text | 150 | 0.80 | 0.60 | 0.62 | 0.26 | 6 | 6 |

## matching = lenient

| approach | stories | P@10 | P@20 | P@50 | R@50 | dup@20 | threads@20 |
|---|---|---|---|---|---|---|---|
| a_mention_graph | 150 | 1.00 | 0.90 | 0.80 | 0.21 | 12 | 6 |
| b_structured_keys | 150 | 0.70 | 0.70 | 0.72 | 0.37 | 6 | 8 |
| baseline_raw_events | 100 | 1.00 | 0.95 | 0.82 | 0.16 | 16 | 3 |
| c_article_text | 150 | 0.90 | 0.90 | 0.82 | 0.29 | 10 | 8 |

## Top 20 per approach (default T) — ✅ = matched entry thread

### a_mention_graph

| # | sources | keywords | match |
|---|---|---|---|
| 1 | 1361 | trump senate election democrats midterm texas house results | ✅ 2026 United States elections (democrat, election, governor, senate) |
| 2 | 909 | trump michigan haley stevens senate sayed rogers race | ✅ 2026 United States elections (abdul, election, michigan, mike) |
| 3 | 888 | trump sayed senate midterm michigan abdul race wins | ✅ 2026 United States elections (abdul, election, michigan, sayed) |
| 4 | 712 | florida crash jet plane south fireball nine killed | ✅ 2026 Palm Beach County Learjet 60 crash (crash, crashe, florida, jet) |
| 5 | 516 | iran trump war talks florida netanyahu nuclear carlson | ✅ 2026 Iran war (hormuz, iran, strait, war) |
| 6 | 426 | texas senate talarico paxton trump midterms race democrats | ✅ 2026 United States elections (democrat, jame, senate, talarico) |
| 7 | 396 | house cornell jeffries hakeem speaker black poised become |  |
| 8 | 378 | russian aid death toll strike ukrainian site missing |  |
| 9 | 375 | midterm trump house data election white democratic but | ✅ 2026 United States elections (election, house, midterm) |
| 10 | 373 | trump democrats midterms election midterm post get aims | ✅ 2026 United States elections (congres, control, election, house) |
| 11 | 358 | alaska senate race letters street beach hastings hotel |  |
| 12 | 353 | democrats trump congress house midterm donald senate gop | ✅ 2026 United States elections (congres, control, election, house) |
| 13 | 330 | maine collins jackson susan troy senate race concedes | ✅ 2026 United States elections (democrat, election, senate) |
| 14 | 330 | texas hinojosa race gov wins election elections spending | ✅ 2026 United States elections (election, hinojosa, talarico, texa) |
| 15 | 313 | lindsay clancy court southwest returns evacuations election flooding |  |
| 16 | 300 | trump strikes iran hormuz strait defensive midterm election | ✅ 2026 Iran war (hormuz, iran, iranian, strait) |
| 17 | 287 | trump redistricting midterm republican election blomstedt conductor great | ✅ 2026 United States elections (election, florida, midterm) |
| 18 | 276 | rogers stevens endorsement senate sayed abdul michigan mike | ✅ 2026 United States elections (abdul, michigan, mike, roger) |
| 19 | 258 | hit meat firms processing freezer attacks cyber fridge |  |
| 20 | 257 | trump midterm senate election redistricting democrat republican house | ✅ 2026 United States elections (election, house, midterm, senate) |

### b_structured_keys

| # | sources | keywords | match |
|---|---|---|---|
| 1 | 4330 | election senate trump midterm democrats race house midterms | ✅ 2026 United States elections (congres, election, house, republican) |
| 2 | 1353 | burnham gbp bid mahmood immigration government christmas calls |  |
| 3 | 1249 | trump midterm iran elections donald voters faces nationwide | ✅ 2026 Iran war (hormuz, iran, iranian, war) |
| 4 | 1142 | iran trump strikes war midterm island hormuz qeshm | ✅ 2026 Iran war (hormuz, iran, strait, war) |
| 5 | 1191 | election israels president government israel trump results building |  |
| 6 | 799 | china castle jumping warning chinese billion chip tragedy |  |
| 7 | 964 | trump israel aid end netanyahu election iran midterm | ✅ 2026 United States elections (election, sayed) |
| 8 | 912 | russian aid centre death toll attack officials rises | ✅ Russian attacks on civilians in the Russo-Ukrainia (aid, attack, centre, russia) |
| 9 | 597 | ban court australia social jones media alan trial |  |
| 10 | 745 | florida crash plane killed nine learjet jet crashes | ✅ 2026 Palm Beach County Learjet 60 crash (beach, crash, crashe, florida) |
| 11 | 780 | france french paris protests school break during election | ✅ 2026 French student protests (france, french, protest, student) |
| 12 | 759 | ukraine russia ceasefire ukraines kherson return region life | ✅ Russian attacks on civilians in the Russo-Ukrainia (attack, russia, ukraine) |
| 13 | 608 | canada budget canadian ottawa federal calls carney trump |  |
| 14 | 640 | russian diesel jersey warns past trump director film | ✅ 2026 United States elections (governor, jame) |
| 15 | 611 | iran trump netanyahu launch strikes talks continue diplomatic |  |
| 16 | 641 | ukraine russia apps emergency cyberattacks ukrainian russian attack | ✅ Russian attacks on civilians in the Russo-Ukrainia (attack, russia, russian, ukraine) |
| 17 | 600 | ant nature nest rarest reserve species stolen demands | ✅ 2026 Binance hack (binance, hack) |
| 18 | 685 | crash florida learjet nine jet south dead officials | ✅ 2026 Palm Beach County Learjet 60 crash (beach, county, crash, crashe) |
| 19 | 524 | germany german berlin spyware among minister must president |  |
| 20 | 372 | delhi india rahul congress gandhi court sir govt | ✅ 2026 anti-CEC protests (delhi, india, protest) |

### baseline_raw_events

| # | sources | keywords | match |
|---|---|---|---|
| 1 | 384 | florida jet crash fireball near busy erupts nosedives | ✅ 2026 Palm Beach County Learjet 60 crash (crash, florida, jet, killed) |
| 2 | 373 | stevens haley michigan senate republican trump democratic sayed | ✅ 2026 United States elections (control, democratic, house, party) |
| 3 | 364 | florida jet fireball crash near busy erupts nosedives | ✅ 2026 Palm Beach County Learjet 60 crash (crash, florida, jet, killed) |
| 4 | 345 | florida jet fireball crash busy near erupts nosedives | ✅ 2026 Palm Beach County Learjet 60 crash (crash, florida, jet, killed) |
| 5 | 340 | florida jet fireball near busy erupts crash nosedives | ✅ 2026 Palm Beach County Learjet 60 crash (crash, florida, jet, killed) |
| 6 | 338 | florida jet fireball busy near erupts nosedives south | ✅ 2026 Palm Beach County Learjet 60 crash (crash, florida, jet, killed) |
| 7 | 332 | florida jet fireball busy near erupts nosedives south | ✅ 2026 Palm Beach County Learjet 60 crash (crash, florida, jet, killed) |
| 8 | 330 | florida jet fireball busy near erupts nosedives south | ✅ 2026 Palm Beach County Learjet 60 crash (crash, florida, jet, killed) |
| 9 | 324 | florida jet fireball near busy erupts nosedives crash | ✅ 2026 Palm Beach County Learjet 60 crash (crash, florida, jet, killed) |
| 10 | 318 | trump democrats midterms post get aims along house | ✅ 2026 United States elections (congres, control, election, house) |
| 11 | 311 | florida jet fireball busy near erupts nosedives south | ✅ 2026 Palm Beach County Learjet 60 crash (crash, florida, jet, killed) |
| 12 | 308 | texas talarico senate race paxton wins against republicans | ✅ 2026 United States elections (senate, talarico, texa) |
| 13 | 307 | aid russian death toll ukrainian strike site missing |  |
| 14 | 305 | florida jet fireball busy near erupts nosedives roadway | ✅ 2026 Palm Beach County Learjet 60 crash (crash, florida, jet, killed) |
| 15 | 286 | russian aid death toll strike ukrainian missing site |  |
| 16 | 278 | florida jet south fireball busy near roadway erupts | ✅ 2026 Palm Beach County Learjet 60 crash (crashe, florida, jet) |
| 17 | 275 | aid russian death toll ukrainian strike missing site |  |
| 18 | 260 | florida jet neighborhood crashes south all board killing | ✅ 2026 Palm Beach County Learjet 60 crash (crash, crashe, florida, jet) |
| 19 | 257 | trump midterm senate election redistricting democrat republican house | ✅ 2026 United States elections (election, house, midterm, senate) |
| 20 | 254 | hit meat firms processing freezer attacks cyber fridge |  |

### c_article_text

| # | sources | keywords | match |
|---|---|---|---|
| 1 | 628 | democrats congress control win senate trump midterm house | ✅ 2026 United States elections (congres, control, election, house) |
| 2 | 739 | florida crash learjet plane jet killed nine beach | ✅ 2026 Palm Beach County Learjet 60 crash (beach, county, crash, crashe) |
| 3 | 637 | sayed michigan senate abdul rogers stevens haley mike | ✅ 2026 United States elections (abdul, election, michigan, mike) |
| 4 | 401 | election midterm results senate elections races house governor | ✅ 2026 United States elections (election, governor, house, midterm) |
| 5 | 530 | israel aid trump end election president billion military |  |
| 6 | 387 | court supreme california ballot mail ballots trump appeal |  |
| 7 | 324 | binance north korea hack billion heist crypto usd | ✅ 2026 Binance hack (billion, binance, hack, korea) |
| 8 | 267 | iran qeshm island trump strikes war midterm hormuz | ✅ 2026 Iran war (hormuz, iran, strait, war) |
| 9 | 277 | texas talarico senate paxton james wins race seat | ✅ 2026 United States elections (democrat, jame, seat, senate) |
| 10 | 225 | supermarket cyberattack freezers food hits second causing bad | ✅ 2026 French supermarket refrigerator hack (causing, cyberattack, europe, european) |
| 11 | 232 | voting early midterm turnout election elections underway final |  |
| 12 | 309 | ukraine russia emergency fake alerts attacks cyber apps | ✅ Russian attacks on civilians in the Russo-Ukrainia (attack, russia, ukraine) |
| 13 | 218 | carolina south senate andrews race annie wins democrat | ✅ 2026 United States elections (democrat, election, senate) |
| 14 | 126 | polls head election voters open voter poll midterm |  |
| 15 | 260 | bomb threats reported flight europe flights school polling |  |
| 16 | 130 | voters amendment approve reproductive virginia constitutional freedom amendments |  |
| 17 | 250 | texas hinojosa abbott race governor gina wins greg | ✅ 2026 United States elections (democrat, gina, governor, hinojosa) |
| 18 | 311 | strait hormuz strikes defensive iranian targets iran official | ✅ 2026 Iran war (carrie, hormuz, iran, iranian) |
| 19 | 281 | judge fbi against case officials hunter biden dismisses |  |
| 20 | 119 | vance midterm iran war losses election blames trump |  |

## Window entries never matched by any approach (top 50, default T)

- 2026-11-02 Salvadoran, Haitian, and Gang Suppression Force soldiers launch an offensive in Plain of the Cul-de-Sac which extends fr
- 2026-11-02 Three people are killed and five more injured in two separated mass shootings at two drug rehabilitation centers in Maza
- 2026-11-02 The Rapid Support Forces launches drone strikes against three distribution stations in Sudan's Kassala and Northern stat
- 2026-11-02 A truck bomb explodes near a military base in Planadas, Tolima Department, Colombia, killing four people, including a ba
- 2026-11-02 An unidentified person throws an IED bomb at the home of Villa El Salvador mayor-elect Marcelino Huamán Cano in Lima, Pe
- 2026-11-02 Uganda begins withdrawing its troops from Somalia, planning to remove all personnel deployed under bilateral and African
- 2026-11-02 Eight people are killed after they were electrocuted when a vehicle comes into contact with a high-voltage power line in
- 2026-11-02 The United States Food and Drug Administration approves the first generic version of lenacapavir, a twice-yearly HIV pre
- 2026-11-02 The Spanish interior ministry reportedly deports 16 migrants, including those from Bangladesh, Cameroon, Nigeria, Senega
- 2026-11-03 Unidentified attackers ambush a police convoy near Gidan-Giye village in Zamfara State, Nigeria, killing at least five p
- 2026-11-03 Spanish author Cristina Fernández Cubas is awarded the 2026 Cervantes Prize to honor her writing in the Spanish language
- 2026-11-03 Five suspected robbers, including two former police personnel, are killed in shootouts with police in Bacoor, Cavite, Ph
- 2026-11-03 Three people are arrested for allegedly wiretapping Indonesian president Prabowo Subianto's phone. (AFP via South China 
- 2026-11-03 Bomb hoaxes target seven flights from several European countries. (BBC News)
- 2026-11-03 The Israeli cruise ship MS Crown Iris is targeted by a false bomb threat, and is searched on Syros, Greece. (Reuters)
- 2026-11-03 Spanish transport minister Óscar Puente resigns after the country experienced two train collision disasters in one year,
- 2026-11-03 In association football, CD Tenerife striker Jesús de Miguel dies following an in-game collision with FC Andorra goalkee
- 2026-11-04 The Bangladeshi garment industry wage board agrees to increase minimum wages following five days of worker protests and 
- 2026-11-04 The Singaporean parliament amends the Transboundary Haze Pollution Act of 2014, introducing arrest powers, permitting tr
- 2026-11-04 The United Kingdom's Office for National Statistics reports that deaths linked to cocaine use have overtaken deaths from
- 2026-11-04 Philippine authorities seize a  shipment of methamphetamine, whose origin is traced to Laos, at the Manila International
- 2026-11-04 Hungary makes Communist-era secret police records publicly accessible through a database containing approximately 60,000
- 2026-11-04 The Neil Gehrels Swift Observatory, a space telescope for studying gamma-ray bursts, re-enters Earth's atmosphere over S
