import re
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("PyMuPDF nao instalado. Execute no terminal: pip install pymupdf")
        sys.exit(1)


CABECALHOS_SECAO = re.compile(
    r"^\s*(?:\d+[\.\)]\s*)?(?:SOLICITA[ÇC][ÃA]O\s+DE\s+(?:ADES[ÃA]O|CANCELAMENTO|MIGRA[ÇC][ÃA]O|INCLUS[ÃA]O|EXCLUS[ÃA]O).*|ADES[ÕO]ES(?:\s+DE\s+DEPENDEN?TES?)?|ADES[ÃA]O\s+(?:DE\s+)?DEPENDEN?TES?|CANCELAMENTOS?|CANCELAMENTO|MIGRA[ÇC][ÕO]ES?|MIGRA[ÇC][ÃA]O|EXCLUS[ÕO]ES?|EXCLUS[ÃA]O)\s*$",
    re.IGNORECASE,
)

FIM_SECAO = re.compile(
    r"^\s*(?:Atenciosamente|Cordialmente|Respeitosamente|Assinado\s+eletronicamente|Documento\s+assinado|Refer[êe]ncia:|Destinat[áa]rio:)\b",
    re.IGNORECASE,
)

TITULOS_PROTEGIDOS = [
    "1. ADESÕES",
    "ADESÕES",
    "ADESOES",
    "1. ADESÃO DE DEPENDENTE",
    "ADESÃO DE DEPENDENTE",
    "ADESAO DE DEPENDENTE",
    "1. ADESÃO DE DEPENDETE",
    "ADESÃO DE DEPENDETE",
    "ADESAO DE DEPENDETE",
    "2. CANCELAMENTOS",
    "CANCELAMENTOS",
    "CANCELAMENTO",
    "1. SOLICITAÇÃO DE ADESÃO PLANO DE SAÚDE ASSEFAZ",
    "SOLICITAÇÃO DE ADESÃO PLANO DE SAÚDE ASSEFAZ",
    "SOLICITACAO DE ADESAO PLANO DE SAUDE ASSEFAZ",
    "SOLICITAÇÃO DE CANCELAMENTO",
    "SOLICITACAO DE CANCELAMENTO",
    "MIGRAÇÕES",
    "MIGRACOES",
    "EXCLUSÕES",
    "EXCLUSOES",
]

PADRAO_LINHA_SOLICITACAO = re.compile(
    r"(?:\bsolicita(?:m)?\s+(?:a\s+)?(?:ades[ãa]o|inclus[ãa]o|cancelamento|migra[çc][ãa]o|exclus[ãa]o)\b|\bdependente\b|\bagregada\b|\bagregado\b)",
    re.IGNORECASE,
)


def normalizar_espacos(texto: str) -> str:
    return re.sub(r"[\s\u00a0]+", " ", texto).strip()


def limpar_nome_arquivo(texto: str) -> str:
    texto = re.sub(r'[\\/*?:"<>|]', "", texto)
    texto = re.sub(r"\s+", "_", texto.strip())
    return texto[:60] or "solicitante"


def extrair_linhas_pdf(caminho_pdf: str) -> list[str]:
    doc = fitz.open(caminho_pdf)
    linhas: list[str] = []
    for pagina in doc:
        texto = pagina.get_text("text")
        for linha in texto.splitlines():
            limpa = normalizar_espacos(linha)
            if limpa:
                linhas.append(limpa)
    doc.close()
    return linhas


def extrair_itens_solicitacoes(linhas: list[str]) -> list[str]:
    itens: list[str] = []
    dentro_secao = False
    item_atual = ""

    for linha in linhas:
        if CABECALHOS_SECAO.match(linha):
            if item_atual:
                itens.append(normalizar_espacos(item_atual))
                item_atual = ""
            dentro_secao = True
            continue

        if dentro_secao and FIM_SECAO.match(linha):
            if item_atual:
                itens.append(normalizar_espacos(item_atual))
                item_atual = ""
            dentro_secao = False
            continue

        if not dentro_secao:
            continue

        if linha.startswith("http://") or linha.startswith("https://"):
            continue

        eh_marcador = bool(re.match(r"^(?:[•\-\*▪◦●○■□]|\d+[\)\.])\s*", linha))
        linha_sem_marcador = re.sub(r"^(?:[•\-\*▪◦●○■□]|\d+[\)\.])\s*", "", linha).strip()

        if eh_marcador or (
            item_atual
            and PADRAO_LINHA_SOLICITACAO.search(item_atual)
            and PADRAO_LINHA_SOLICITACAO.search(linha_sem_marcador)
        ):
            itens.append(normalizar_espacos(item_atual))
            item_atual = linha_sem_marcador
        else:
            if item_atual:
                item_atual = f"{item_atual} {linha_sem_marcador}".strip()
            else:
                item_atual = linha_sem_marcador

    if item_atual:
        itens.append(normalizar_espacos(item_atual))

    itens_filtrados = [it for it in itens if not CABECALHOS_SECAO.match(it)]

    unicos: list[str] = []
    vistos: set[str] = set()
    for item in itens_filtrados:
        chave = item.lower()
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(item)
    return unicos


def extrair_nomes_de_item(item_texto: str) -> list[str]:
    padrao_nome = re.compile(
        r"\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+(?:\s+(?:de|da|do|dos|das|e)\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+|\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+){1,5}\b"
    )
    nomes = [normalizar_espacos(m.group(0)) for m in padrao_nome.finditer(item_texto)]
    resultado: list[str] = []
    vistos: set[str] = set()
    for n in nomes:
        if n.lower() not in vistos:
            vistos.add(n.lower())
            resultado.append(n)
    return resultado


def gerar_pdfs_por_item(
    pdf_entrada: str,
    pasta_saida: str,
    itens_solicitacao: list[str],
    modo_censura: str = "linha_inteira",
    dpi: int = 200,
) -> tuple[list[Path], list[str]]:
    Path(pasta_saida).mkdir(parents=True, exist_ok=True)
    arquivos_gerados: list[Path] = []
    relatorio: list[str] = []
    zoom = dpi / 72.0
    matriz = fitz.Matrix(zoom, zoom)

    for indice, item_manter in enumerate(itens_solicitacao, start=1):
        outros_itens = [it for it in itens_solicitacao if it != item_manter]
        doc_temp = fitz.open(pdf_entrada)
        total_tarjas = 0

        for pagina in doc_temp:
            rects_protegidos = []
            for titulo in TITULOS_PROTEGIDOS:
                rects_protegidos.extend(pagina.search_for(titulo))

            for item_tarjar in outros_itens:
                if modo_censura == "apenas_nomes":
                    alvos = extrair_nomes_de_item(item_tarjar)
                else:
                    # Busca a frase inteira e tambem cada nome/parte para garantir cobertura
                    alvos = [item_tarjar] + extrair_nomes_de_item(item_tarjar)

                rects_encontrados = []
                for alvo in alvos:
                    if not alvo:
                        continue
                    rects_encontrados.extend(pagina.search_for(alvo))

                # Unifica retangulos da mesma linha para formar uma tarja limpa
                rects_filtrados = []
                for rect in rects_encontrados:
                    if any(rect.intersects(rp) for rp in rects_protegidos):
                        continue
                    rects_filtrados.append(rect)

                for rect in rects_filtrados:
                    rect_tarja = fitz.Rect(
                        rect.x0 - 3.0,
                        rect.y0 - 2.0,
                        rect.x1 + 3.0,
                        rect.y1 + 2.0,
                    )
                    pagina.add_redact_annot(rect_tarja, fill=(0, 0, 0))
                    total_tarjas += 1

            pagina.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        doc_final = fitz.open()
        for pagina in doc_temp:
            pix = pagina.get_pixmap(matrix=matriz, alpha=False)
            pag_nova = doc_final.new_page(width=pagina.rect.width, height=pagina.rect.height)
            pag_nova.insert_image(pag_nova.rect, pixmap=pix)

        nomes_item = extrair_nomes_de_item(item_manter)
        rotulo_base = nomes_item[0] if nomes_item else f"item_{indice}"
        nome_arq = f"{indice:02d}_{limpar_nome_arquivo(rotulo_base)}.pdf"
        caminho_final = Path(pasta_saida) / nome_arq

        try:
            doc_final.save(str(caminho_final))
        except Exception:
            caminho_final = Path(pasta_saida) / f"{indice:02d}_{limpar_nome_arquivo(rotulo_base)}_novo.pdf"
            doc_final.save(str(caminho_final))

        doc_final.close()
        doc_temp.close()
        arquivos_gerados.append(caminho_final)
        relatorio.append(f"{caminho_final.name} -> {total_tarjas} tarja(s)")

    return arquivos_gerados, relatorio


class AppCensuraOffline:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Censura Automatica de Oficios (Offline)")
        self.root.geometry("880x670")

        self.pdf_selecionado: str = ""

        frame_topo = tk.Frame(root, padx=10, pady=8)
        frame_topo.pack(fill=tk.X)

        tk.Label(frame_topo, text="PDF do Oficio:").pack(side=tk.LEFT)
        self.lbl_arquivo = tk.Label(
            frame_topo, text="Nenhum arquivo selecionado", fg="gray", anchor="w"
        )
        self.lbl_arquivo.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)

        tk.Button(frame_topo, text="Escolher PDF...", command=self.escolher_pdf).pack(side=tk.RIGHT)

        frame_param = tk.Frame(root, padx=10, pady=4)
        frame_param.pack(fill=tk.X)

        tk.Label(frame_param, text="Parametro de censura:").pack(side=tk.LEFT)
        self.cmb_modo = ttk.Combobox(
            frame_param,
            state="readonly",
            width=34,
            values=[
                "Linha inteira + nomes (padrao)",
                "Apenas nomes dos outros itens",
            ],
        )
        self.cmb_modo.current(0)
        self.cmb_modo.pack(side=tk.LEFT, padx=8)

        tk.Label(
            root,
            text="Itens detectados nas secoes (1 item por linha — apenas a linha da vez fica visivel; os demais sao tarjados):",
            anchor="w",
            padx=10,
        ).pack(fill=tk.X)

        self.txt_itens = scrolledtext.ScrolledText(root, height=16, padx=6, pady=4)
        self.txt_itens.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 10))

        frame_acoes = tk.Frame(root, padx=10, pady=8)
        frame_acoes.pack(fill=tk.X)

        tk.Button(
            frame_acoes,
            text="Re-ler itens do PDF",
            command=self.carregar_itens,
        ).pack(side=tk.LEFT)

        tk.Button(
            frame_acoes,
            text="Gerar PDFs Separados (Offline)",
            bg="#1b5e20",
            fg="white",
            font=("TkDefaultFont", 10, "bold"),
            command=self.executar_geracao,
        ).pack(side=tk.RIGHT)

    def escolher_pdf(self) -> None:
        caminho = filedialog.askopenfilename(
            title="Selecione o PDF do oficio",
            filetypes=[("Arquivos PDF", "*.pdf"), ("Todos os arquivos", "*.*")],
        )
        if caminho:
            self.pdf_selecionado = caminho
            self.lbl_arquivo.config(text=caminho, fg="black")
            self.carregar_itens()

    def carregar_itens(self) -> None:
        if not self.pdf_selecionado:
            messagebox.showwarning("Atencao", "Escolha um arquivo PDF primeiro.")
            return
        try:
            linhas = extrair_linhas_pdf(self.pdf_selecionado)
            itens = extrair_itens_solicitacoes(linhas)
            self.txt_itens.delete("1.0", tk.END)
            if itens:
                self.txt_itens.insert(tk.END, "\n".join(itens))
            else:
                messagebox.showinfo(
                    "Aviso",
                    "Nao encontrei itens automaticamente sob ADESOES/CANCELAMENTOS. Voce pode colar ou digitar cada item em uma linha.",
                )
        except Exception as e:
            messagebox.showerror("Erro ao ler PDF", str(e))

    def executar_geracao(self) -> None:
        if not self.pdf_selecionado:
            messagebox.showwarning("Atencao", "Selecione um arquivo PDF primeiro.")
            return

        itens = [
            normalizar_espacos(linha)
            for linha in self.txt_itens.get("1.0", tk.END).splitlines()
            if linha.strip()
        ]
        if not itens:
            messagebox.showwarning(
                "Atencao",
                "Nenhum item encontrado ou informado para gerar os PDFs separados.",
            )
            return

        modo_texto = self.cmb_modo.get()
        modo_censura = "apenas_nomes" if "Apenas nomes" in modo_texto else "linha_inteira"

        pasta_base = Path(self.pdf_selecionado).parent
        nome_base = limpar_nome_arquivo(Path(self.pdf_selecionado).stem)
        pasta_saida = str(pasta_base / f"oficios_separados_{nome_base}")

        try:
            gerados, relatorio = gerar_pdfs_por_item(
                pdf_entrada=self.pdf_selecionado,
                pasta_saida=pasta_saida,
                itens_solicitacao=itens,
                modo_censura=modo_censura,
                dpi=200,
            )
            resumo = "\n".join(relatorio)
            messagebox.showinfo(
                "Concluido",
                f"{len(gerados)} PDF(s) gerado(s) em:\n{pasta_saida}\n\n{resumo}",
            )
        except Exception as e:
            messagebox.showerror("Erro ao gerar PDFs", str(e))


if __name__ == "__main__":
    raiz = tk.Tk()
    app = AppCensuraOffline(raiz)
    raiz.mainloop()