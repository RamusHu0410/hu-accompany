Ramus execpted recieve: 
(We compare to multiple good recording)

WE WILL AVERAGE SAMPLE RECORDING UP FOR AN OVERALL SAMPLE RECORDING

Good_recording: \[{notevalue:int(hz), duration:int(s), volumn:int(0\~1), ...}]

User_recording: \[{notevalue:int(hz), duration:int(s), volumn:int(0\~1), ...}]

Rating will be = 
      
      factor1\*abs(good_recording[index][notevalue]-user_recording[index][notevalue]) + factor2\*abs(good_recording[index][duration]-user_recording[index][duration]) + ... + factorsomething\*abs(user_recording[index][duration]-user_recording[index-1][duration]) + factoranotherthing\*abs(user_recording[index][duration]-user_recording[index-2][duration])+ ...

Concerns about rubato:

Check if the tempo is decreasing / increasing in sequence

Next step: learn reinforcement learning


Get the machine learning out of here we are just random high school student who vibecode the entire project...




To Kelvin:

The result should be written in the following structure

{"query": "Piano Sonata No.14", "results": [{"name": "Piano Sonata No.14, Op.27 No.2", "composer": "Beethoven, Ludwig van", "url": "https://imslp.org/wiki/Piano_Sonata_No.14,_Op.27_No.2_(Beethoven,_Ludwig_van)"}, {"name": "Piano Sonata No.14 in C minor, K.457", "composer": "Mozart, Wolfgang Amadeus", "url": "https://imslp.org/wiki/Piano_Sonata_No.14_in_C_minor,_K.457_(Mozart,_Wolfgang_Amadeus)"}, {"name": "Piano Sonata No.14, Op.39 No.1", "composer": "Dussek, Jan Ladislav", "url": "https://imslp.org/wiki/Piano_Sonata_No.14,_Op.39_No.1_(Dussek,_Jan_Ladislav)"}, {"name": "Piano Sonata in B-flat major, Op.26", "composer": "M\u00fcller, August Eberhard", "url": "https://imslp.org/wiki/Piano_Sonata_in_B-flat_major,_Op.26_(M\u00fcller,_August_Eberhard)"}, {"name": "Piano Sonata No.14", "composer": "Haydn, Joseph", "url": "https://imslp.org/wiki/Piano_Sonata_No.14_(Haydn,_Joseph)"}, {"name": "Piano Sonata No.14, tbp 95", "composer": "Novegno, Roberto", "url": "https://imslp.org/wiki/Piano_Sonata_No.14,_tbp_95_(Novegno,_Roberto)"}, {"name": "Adoremus - 4pt harmonization set to Beethovens piano sonata no.14, mov.1", "composer": "McManus, Stephen", "url": "https://imslp.org/wiki/Adoremus_-_4pt_harmonization_set_to_Beethovens_piano_sonata_no.14,_mov.1_(McManus,_Stephen)"}, {"name": "Piano Sonata No.14 Hob.XVI:3, C major", "composer": "Haydn, Joseph", "url": "https://imslp.org/wiki/Piano_Sonata_No.14_Hob.XVI:3,_C_major_(Haydn,_Joseph)"}, {"name": "Piano Sonata No.14", "composer": "Drozdov, Vladimir", "url": "https://imslp.org/wiki/Piano_Sonata_No.14_(Drozdov,_Vladimir)"}, {"name": "Piano Sonata No.14 in D major", "composer": "Praeger, Ferdinand", "url": "https://imslp.org/wiki/Piano_Sonata_No.14_in_D_major_(Praeger,_Ferdinand)"}, {"name": "Piano Sonata in A minor, D.784", "composer": "Schubert, Franz", "url": "https://imslp.org/wiki/Piano_Sonata_in_A_minor,_D.784_(Schubert,_Franz)"}, {"name": "Piano Sonata No.14, Op.45", "composer": "Ngo, Ethan", "url": "https://imslp.org/wiki/Piano_Sonata_No.14,_Op.45_(Ngo,_Ethan)"}, {"name": "Piano Sonata No.14, Op.99", "composer": "Alexander, Robert", "url": "https://imslp.org/wiki/Piano_Sonata_No.14,_Op.99_(Alexander,_Robert)"}]}%           



{
    "title": "3 Nouvelles \u00e9tudes, B.130",
    "composer": "Chopin, Fr\u00e9d\u00e9ric",
    "imslp_url": "https://imslp.org/wiki/3_Nouvelles_\u00e9tudes,_B.130_(Chopin,_Fr\u00e9d\u00e9ric)",
    "choices": [
        {
            "id": "228",
            "name": "Piano Solo",
            "instrumentation": "Piano",
            "type": "Original Score",
            "imslp_url": "https://imslp.org/wiki/Special:ImagefromIndex/399450",
            "movement": null,
            "arranger": null,
            "editor": null,
            "file_name": "PMLP02634-BnF_btv1b52500458h.pdf"
        },
        {
            "id": "229",
            "name": "Piano Solo",
            "instrumentation": "Piano",
            "type": "Original Score",
            "imslp_url": "https://imslp.org/wiki/Special:ImagefromIndex/534261",
            "movement": "Selections",
            "arranger": null,
            "editor": "Romain Behar",
            "file_name": "PMLP02634-TroisNouvellesEtudes-n1_Chopin.pdf"
        },
        {
            "id": "230",
            "name": "Violin and Piano Arrangement",
            "instrumentation": "Violin + Piano",
            "type": "Arrangement",
            "imslp_url": "https://imslp.org/wiki/Special:ImagefromIndex/1002125",
            "movement": "Andantino (No.1)",
            "arranger": "Dhanrajani",
            "editor": null,
            "file_name": "PMLP2634-Nouvelle_Etude_No_1.pdf"
        },
        {
            "id": "231",
            "name": "Piano 4 Hands Arrangement",
            "instrumentation": "Piano 4 Hands",
            "type": "Arrangement",
            "imslp_url": "https://imslp.org/wiki/Special:ImagefromIndex/77380",
            "movement": "Allegretto (No.3)",
            "arranger": null,
            "editor": null,
            "file_name": "PMLP02634-Chopin_Frederic_Etude_B.130_3_piano4hands.pdf"
        }
    ]