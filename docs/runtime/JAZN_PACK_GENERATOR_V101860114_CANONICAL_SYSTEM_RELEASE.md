# Jaźń Pack Generator 10.1.86.0.114 — canonical SYSTEM release

## Rozdzielenie kontraktów

`MEMORY` nadal jest selected-folder byte-exact snapshotem. `SYSTEM` i część systemowa `SYSTEM+MEMORY` nie są już kopiowane z working tree.

Dla checkoutu Git:

```text
clean HEAD
  -> create_release_staging()
  -> immutable Git blobs
  -> SOURCE_PROVENANCE.json
  -> PACKAGE_INTEGRITY_MANIFEST.json
  -> ZIP
  -> safe clean-room extract
  -> inner integrity + provenance reverify
  -> publish/split
```

Git może przechowywać tekst z LF w indeksie i jednocześnie wystawiać CRLF w working tree zależnie od `eol`, konfiguracji i platformy. Dlatego release bytes są pobierane z kanonicznych obiektów Git, a nie z reprezentacji checkoutu.

## Fail-closed

Runnable SYSTEM nie jest publikowany, gdy:

- working tree jest brudny;
- selected commit nie jest clean current HEAD;
- canonical staging nie przechodzi integralności/provenance;
- ZIP zawiera traversal, symlink, duplicate/casefold-collision;
- ZIP member SHA nie odpowiada stagingowi;
- po ekstrakcji wewnętrzny manifest lub provenance nie przechodzi ponownej walidacji.

## MEMORY

MEMORY zachowuje dokładne bajty wskazanego katalogu. `.gitattributes` nie zmienia jego danych i pozostaje diagnostyką folder snapshotu.

## Źródła

- https://git-scm.com/docs/gitattributes
- https://docs.python.org/3/library/zipfile.html
