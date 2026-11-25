[🇧🇷 Português](README.md) | **🇺🇸 English**

# IBS/CBS Auditor: check Brazilian e-invoices for the 2026 tax reform

[![CI](https://github.com/gavicoding/auditor-ibs-cbs/actions/workflows/ci.yml/badge.svg)](https://github.com/gavicoding/auditor-ibs-cbs/actions/workflows/ci.yml)
[![Use in the browser](https://img.shields.io/badge/use%20in%20the%20browser-free-1a7f5a)](https://gavicoding.github.io/auditor-ibs-cbs/)
![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## In plain words

Brazil's consumption tax reform added two new taxes, **IBS** and **CBS**. Since 2026, electronic tax documents must carry an IBS/CBS group with the right **CST** and **cClassTrib** codes. Several mistakes get a document rejected by the tax authority (SEFAZ) or leave it wrong:
- a wrong code pair;
- a reduced rate (such as the basic food basket) applied to a product that is not on the law's list;
- totals one cent off;
- amounts that do not add up.

This tool reads the XML files, one or thousands at a time, and tells you **what is wrong, on which item, how to fix it and which SEFAZ rejection it causes**. Each finding cites the rule and page of the official technical note (NT 2025.002-RTC v1.53).

👉 **[Use it in the browser](https://gavicoding.github.io/auditor-ibs-cbs/)**: nothing leaves your computer.

**Documents:** NF-e, NFC-e, CT-e, CT-e OS, BP-e, NF3-e and national NFS-e.

**What you gain**

- **The rejection before you send the document:** the code, rule, NT page and whether the rule is already enforced in production.
- **The most expensive mistake caught:** a product using a reduced-rate code without being on the law's list, with the official exceptions and a suggestion of codes the product may use.
- **A batch summary** and spreadsheets for accountants, plus **NCM lookup**.
- **Always up to date:**
  - tables refreshed daily from the official Federal Revenue calculator (MIT);
  - daily watchers that open an issue when a new regulation is published.

## Ways to use it

| Option | For |
| :--- | :--- |
| Web page | Accountants and anyone, no install |
| Windows `.exe` | Offices that do not install anything |
| Python CLI and library | Developers, automation, CI |
| Local HTTP API and Docker | Any language (Delphi, C#, Java, PHP, Node) |
| JavaScript package | Web ERPs, Node and TypeScript |
| SQL package (SQL Server, PostgreSQL, MySQL, SQLite) | Checks inside the ERP database |
| GitHub Action | Testing an invoice issuer on every change |

All of them share the same tables and rules:
- the Python and JavaScript versions are compared on thousands of random documents on every change;
- the SQL package runs on real PostgreSQL 16, MySQL 8 and SQL Server 2022 in CI.

See the [Portuguese README](README.md) for commands, the full rule table and rejection codes. Messages and commands are in Portuguese because the audience is Brazilian.

## Disclaimer

Independent, unofficial project, not affiliated with the Receita Federal, Serpro or any state tax office. It does not replace the tax authority's validation or professional advice. All example XML files are fictional.

## License

[MIT](LICENSE). Tables and schemas derived from the Receita Federal calculator keep its MIT license; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
