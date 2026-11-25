"""auditor-ibs-cbs: confere o IBS/CBS de XMLs de NF-e e NFC-e contra as tabelas oficiais."""

from .leitor import Nota, XMLInvalido, ler_arquivo, ler_bytes
from .regras import Achado, Resultado, auditar
from .tabelas import Tabelas, carregar

__version__ = "1.0.0"
__all__ = ["Achado", "Nota", "Resultado", "Tabelas", "XMLInvalido", "auditar", "carregar", "ler_arquivo", "ler_bytes"]
