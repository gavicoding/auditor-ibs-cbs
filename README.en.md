[🇧🇷 Português](README.md) | **🇺🇸 English**

# IBS/CBS Auditor: check Brazilian e-invoices for the 2026 tax reform

[![CI](https://github.com/gavicoding/auditor-ibs-cbs/actions/workflows/ci.yml/badge.svg)](https://github.com/gavicoding/auditor-ibs-cbs/actions/workflows/ci.yml)
[![Use in the browser](https://img.shields.io/badge/use%20in%20the%20browser-free-1a7f5a)](https://gavicoding.github.io/auditor-ibs-cbs/)
![Python](https://img.shields.io/badge/python-3.10%20to%203.13-blue)
![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## In plain words

Brazil's consumption tax reform added two new taxes, **IBS** and **CBS**. Since 2026, electronic tax documents must carry an IBS/CBS group with the right **CST** and **cClassTrib** codes. A wrong code pair, a retired code, a reduced rate (such as the basic food basket) applied to a product that is not on the law's list, or values that do not add up get the document rejected or leave it wrong in the eyes of the tax authority.

Supported documents: NF-e, NFC-e, CT-e, CT-e OS, BP-e, NF3-e and the national NFS-e.

This tool reads invoice XML files, one or thousands at a time, and tells you **what is wrong, on which item and how to fix it**, in plain Portuguese. It checks against the **official tables** published by Brazil's Federal Revenue (Receita Federal): CST, cClassTrib, which products (NCM) and services (NBS) each code accepts, the law's annexes and reference rates.

👉 **[Use it in the browser](https://gavicoding.github.io/auditor-ibs-cbs/)**: drop XML files or a .zip. **Nothing leaves your computer**; everything runs in the browser.

**What you gain**

- Problems found before the tax authority finds them, for a whole folder at once (including .zip files).
- Explanations people can act on, with the legal basis when there is one, not just error codes.
- Catches the most expensive mistake: a product using a reduced-rate code without being on the law's list.
- A batch summary (top problems, problems by code, by product and by issuer, totals by code) and CSV spreadsheets.
- Look up a product code (NCM) to see which reduced-rate codes it may use.
- Official tables kept up to date by a weekly job that tracks the Receita Federal's public repository.
- Zero install in the browser, zero dependencies in Python. Reports never include the buyer's personal data.

## What is checked

Missing IBS/CBS group; CST and cClassTrib that do not exist, were not valid on the date, do not match each other or are not allowed for the document type; products (NCM) or services (NBS) not on the code's list, honoring official exceptions; unknown NCM; layout format and required fields; reduction, effective rate and deferral different from the official formulas; amounts that do not match base × rate (banker's rounding, R$ 0.01 tolerance), including presumed credit, government purchases, regular taxation and single-phase fuel taxation; totals different from the sum of the items; optional validation against the official XSD (`--xsd`). See the [Portuguese README](README.md#o-que-é-conferido) for the full rule list (`AIC-0xx` codes).

## Command line and library

```bash
pip install git+https://github.com/gavicoding/auditor-ibs-cbs.git

auditor-ibs-cbs auditar invoices/                  # audit a folder (and .zip files inside it)
auditor-ibs-cbs auditar invoices/ -f html -o report.html
auditor-ibs-cbs auditar invoices/ --falhar-em erro  # exit code 1 on errors, for CI
auditor-ibs-cbs consultar 200003                   # explain a cClassTrib code and the NCMs it accepts
auditor-ibs-cbs consultar 10063021                 # which reduced-rate codes accept this product (NCM)
auditor-ibs-cbs tabelas                            # which official table version is in use
```

```python
from auditor_ibs_cbs import auditar, carregar, ler_arquivo

result = auditar(ler_arquivo("invoice.xml"), carregar())
for finding in result.achados:
    print(finding.codigo, finding.gravidade, finding.item, finding.titulo)
```

Messages and command names are in Portuguese because the audience is Brazilian.

## Where the tables come from

CST, cClassTrib, document-type links, NCM/NBS lists with exceptions, the law's annexes, reduction percentages, reference rates, the NCM table and the official XSD schemas are extracted from the public repository of the **[Receita Federal tax calculator](https://github.com/ReceitaFederal/calculadora-rtc-regime-regular)** (MIT license) by [`ferramentas/exportar_tabelas.py`](ferramentas/exportar_tabelas.py), which only reads that repository's SQL migration files. A weekly workflow opens a pull request when a new table version is published. For full tax calculation, use the official calculator; this project complements it by auditing invoices already issued, in bulk.

## Disclaimer

Independent, unofficial project, not affiliated with the Receita Federal, Serpro or any state tax office. It helps find problems but does not replace the tax authority's validation or professional tax advice. All XML files in `exemplos/` are fictional.

## Development

```bash
pip install -e ".[dev]" && pytest
node --test tests/web/paridade.test.mjs
python ferramentas/fuzz_paridade.py /tmp/fuzz 2000 && node tests/web/fuzz.mjs /tmp/fuzz
```

The browser version ([`docs/auditor.js`](docs/auditor.js)) and the Python version follow the same rules and are checked against the same expected results plus a randomized parity test on every change.

## License

[MIT](LICENSE). Tables derived from the Receita Federal calculator keep its original MIT license; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
