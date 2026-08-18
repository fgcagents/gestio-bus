# Optimitzacions OCR i rendiment

## Canvis aplicats

- EasyOCR carrega només el model anglès, suficient per a matrícules alfanumèriques.
- La fotografia es corregeix segons l'orientació EXIF, es retalla al centre i es
  limita a 1280 x 720 abans de passar-la al detector.
- El reconeixement utilitza una llista restringida de caràcters, descodificació
  `greedy` i retorna confiança i coordenades.
- Les deteccions s'avaluen per separat. No es concatenen textos independents.
- El candidat es tria principalment per confiança, amb preferència secundària
  per les deteccions pròximes al centre.
- La consulta del registre obert i la comprovació de la flota comparteixen una
  sola connexió i una sola consulta SQL.
- S'han eliminat els buidatges globals de `st.cache_data`. Només s'invaliden el
  comptador de vehicles esperant i la taula d'últims moviments.
- El botó d'actualització utilitza un callback i no provoca un segon rerun.

## Afinament del frontend

- Els cinc títols de pàgina reutilitzen les icones Material del panell de
  navegació.
- Els subtítols descriptius es mantenen discrets, mentre que els estats que
  requereixen atenció es mostren com avisos amb color i icona.
- Una matrícula no catalogada mostra un avís destacat abans de les dades del nou
  autocar.
- Les arribades preparades, les sortides pendents, els errors i les
  confirmacions utilitzen un llenguatge visual coherent.

## Validació recomanada abans de desplegar

Provar un conjunt de fotografies reals en diferents condicions: llum natural,
reflexos, poca llum, matrícula inclinada i distàncies diferents. Cal mesurar el
temps de primera lectura, el de lectures posteriors i la taxa d'encert.

Si moltes matrícules queden fora del retall, cal ampliar els percentatges de
`preparar_imatge_ocr`. Si EasyOCR divideix sovint una matrícula en dos fragments,
cal afegir una agrupació geomètrica de fragments adjacents abans de validar-los.
