from pathlib import Path
from sklearn.cluster import DBSCAN
import argparse
import json
import re
import shutil
import subprocess
from tqdm import tqdm
import numpy as np
import pandas as pd


# ============================================================
# EXTENSÕES SUPORTADAS
# ============================================================

EXTENSOES_IMAGEM = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic", ".heif"
}

EXTENSOES_VIDEO = {
    ".mp4", ".mov", ".avi", ".mkv", ".3gp", ".m4v"
}

EXTENSOES_SUPORTADAS = EXTENSOES_IMAGEM | EXTENSOES_VIDEO


# ============================================================
# ARGUMENTOS DE TERMINAL
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Agrupa imagens e vídeos por proximidade geográfica "
            "usando metadados GPS."
        )
    )

    parser.add_argument(
        "-i", "--input",
        type=Path,
        required=True,
        help="Pasta onde estão as imagens e vídeos."
    )

    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("midias_agrupadas"),
        help="Pasta de saída. Padrão: midias_agrupadas."
    )

    parser.add_argument(
        "-d", "--distancia",
        type=float,
        default=300,
        help="Distância máxima em metros para agrupar mídias próximas. Padrão: 300."
    )

    parser.add_argument(
        "--mover",
        action="store_true",
        help="Move os arquivos em vez de copiá-los."
    )

    parser.add_argument(
        "--min-samples",
        type=int,
        default=1,
        help=(
            "Número mínimo de mídias para formar uma região no DBSCAN. "
            "Padrão: 1, ou seja, arquivos isolados também viram grupo."
        )
    )

    return parser.parse_args()


# ============================================================
# UTILITÁRIOS
# ============================================================

def verificar_exiftool():
    """
    Verifica se o exiftool está instalado no sistema.
    """
    try:
        subprocess.run(
            ["exiftool", "-ver"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
    except FileNotFoundError:
        raise RuntimeError(
            "ExifTool não encontrado. Instale com:\n"
            "sudo apt install libimage-exiftool-perl"
        )


def tipo_midia(arquivo):
    """
    Retorna o tipo de mídia com base na extensão.
    """
    ext = arquivo.suffix.lower()

    if ext in EXTENSOES_IMAGEM:
        return "imagem"

    if ext in EXTENSOES_VIDEO:
        return "video"

    return "desconhecido"


def listar_midias(pasta):
    """
    Lista imagens e vídeos dentro da pasta, incluindo subpastas.
    """
    return [
        p for p in pasta.rglob("*")
        if p.is_file() and p.suffix.lower() in EXTENSOES_SUPORTADAS
    ]


# ============================================================
# LEITURA DE METADADOS COM EXIFTOOL
# ============================================================

def ler_metadados_exiftool(arquivo):
    """
    Lê metadados de um arquivo usando exiftool em formato JSON.
    Funciona para imagens e vídeos.
    """
    try:
        resultado = subprocess.run(
            [
                "exiftool",
                "-json",
                "-n",
                str(arquivo)
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )

        dados = json.loads(resultado.stdout)

        if not dados:
            return None

        return dados[0]

    except subprocess.CalledProcessError as e:
        print(f"[ERRO] ExifTool falhou em {arquivo}: {e.stderr}")
        return None

    except json.JSONDecodeError:
        print(f"[ERRO] Não foi possível decodificar JSON de {arquivo}")
        return None


# ============================================================
# CONVERSÃO E EXTRAÇÃO DE GPS
# ============================================================

def limpar_numero(valor):
    """
    Converte valores numéricos vindos como string para float.
    """
    if valor is None:
        return None

    if isinstance(valor, (int, float)):
        return float(valor)

    valor = str(valor).strip()
    valor = valor.replace(",", ".")

    try:
        return float(valor)
    except ValueError:
        return None


def extrair_de_location_string(location):
    """
    Extrai latitude e longitude de strings comuns em vídeos,
    principalmente metadados QuickTime.

    Exemplos possíveis:
    - '-14.798694-39.033000/'
    - '-14.798694, -39.033000'
    - '+14.798694-039.033000/'
    """
    if not location:
        return None

    texto = str(location).strip()

    # Padrão com dois números com sinal: -14.798694-39.033000/
    matches = re.findall(r"([+-]\d+(?:\.\d+)?)", texto)

    if len(matches) >= 2:
        lat = float(matches[0])
        lon = float(matches[1])
        return lat, lon

    # Padrão separado por vírgula ou espaço
    matches = re.findall(r"[-+]?\d+(?:\.\d+)?", texto)

    if len(matches) >= 2:
        lat = float(matches[0])
        lon = float(matches[1])
        return lat, lon

    return None


def extrair_gps(metadados):
    """
    Tenta extrair latitude e longitude a partir de diferentes campos possíveis
    retornados pelo ExifTool.

    Para imagens, geralmente aparecem:
    - GPSLatitude
    - GPSLongitude

    Para vídeos, podem aparecer:
    - GPSCoordinates
    - GPSPosition
    - Location
    - QuickTime:Location
    - Composite:GPSPosition
    """

    if not metadados:
        return None

    # Caso mais comum em imagens com -n:
    # GPSLatitude: -14.798694
    # GPSLongitude: -39.033000
    lat = limpar_numero(metadados.get("GPSLatitude"))
    lon = limpar_numero(metadados.get("GPSLongitude"))

    if lat is not None and lon is not None:
        return lat, lon

    # Campos comuns em vídeos ou metadados compostos
    campos_possiveis = [
        "GPSPosition",
        "GPSCoordinates",
        "Location",
        "QuickTime:Location",
        "Composite:GPSPosition",
        "Keys:GPSCoordinates",
        "UserData:GPSCoordinates"
    ]

    for campo in campos_possiveis:
        valor = metadados.get(campo)

        gps = extrair_de_location_string(valor)

        if gps is not None:
            return gps

    return None


# ============================================================
# AGRUPAMENTO COM DBSCAN
# ============================================================

def agrupar_por_gps(df, distancia_metros, min_samples=1):
    """
    Agrupa coordenadas próximas usando DBSCAN com distância haversine.

    A distância haversine é adequada para latitude/longitude,
    pois considera a curvatura da Terra.
    """
    raio_terra_m = 6_371_000

    coords = df[["latitude", "longitude"]].to_numpy()
    coords_rad = np.radians(coords)

    eps_rad = distancia_metros / raio_terra_m

    modelo = DBSCAN(
        eps=eps_rad,
        min_samples=min_samples,
        metric="haversine"
    )

    labels = modelo.fit_predict(coords_rad)

    df = df.copy()
    df["grupo"] = labels

    return df


# ============================================================
# SALVAR ARQUIVOS AGRUPADOS
# ============================================================

def salvar_agrupamentos(df, pasta_saida, mover=False):
    """
    Copia ou move os arquivos para pastas por grupo.

    Se grupo = -1, significa ruído no DBSCAN quando min_samples > 1.
    """
    pasta_saida.mkdir(parents=True, exist_ok=True)

    for idx, row in df.iterrows():
        grupo = int(row["grupo"])
        origem = Path(row["arquivo"])

        if grupo == -1:
            nome_pasta = "sem_grupo"
        else:
            nome_pasta = f"regiao_{grupo:03d}"

        pasta_grupo = pasta_saida / nome_pasta
        pasta_grupo.mkdir(parents=True, exist_ok=True)

        destino = pasta_grupo / origem.name

        # Evita sobrescrever arquivos com mesmo nome
        if destino.exists():
            destino = pasta_grupo / f"{origem.stem}_{idx}{origem.suffix}"

        if mover:
            shutil.move(str(origem), str(destino))
        else:
            shutil.copy2(str(origem), str(destino))


# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================

def main():
    args = parse_args()

    pasta_entrada = args.input
    pasta_saida = args.output
    distancia_metros = args.distancia
    mover_arquivos = args.mover
    min_samples = args.min_samples

    if not pasta_entrada.exists():
        print(f"[ERRO] A pasta de entrada não existe: {pasta_entrada}")
        return

    if not pasta_entrada.is_dir():
        print(f"[ERRO] O caminho informado não é uma pasta: {pasta_entrada}")
        return

    try:
        verificar_exiftool()
    except RuntimeError as e:
        print(e)
        return

    print("Iniciando leitura das mídias...")
    print(f"Pasta de entrada: {pasta_entrada}")
    print(f"Pasta de saída: {pasta_saida}")
    print(f"Distância de agrupamento: {distancia_metros} metros")
    print(f"min_samples: {min_samples}")
    print(f"Modo: {'mover arquivos' if mover_arquivos else 'copiar arquivos'}")
    print("-" * 70)

    arquivos = listar_midias(pasta_entrada)
    print(f"Total de mídias encontradas para análise: {len(arquivos)}")
    if not arquivos:
        print("[AVISO] Nenhuma imagem ou vídeo foi encontrado na pasta de entrada.")
        return

    registros = []
    sem_gps = []

    for arquivo in tqdm(arquivos, desc="Lendo metadados GPS"):
        metadados = ler_metadados_exiftool(arquivo)
        gps = extrair_gps(metadados)

        if gps is None:
            sem_gps.append(str(arquivo))
            continue

        lat, lon = gps

        registros.append({
            "arquivo": str(arquivo),
            "nome_arquivo": arquivo.name,
            "extensao": arquivo.suffix.lower(),
            "tipo": tipo_midia(arquivo),
            "latitude": lat,
            "longitude": lon
        })

    pasta_saida.mkdir(parents=True, exist_ok=True)

    if sem_gps:
        sem_gps_path = pasta_saida / "midias_sem_gps.txt"

        with open(sem_gps_path, "w", encoding="utf-8") as f:
            for item in sem_gps:
                f.write(item + "\n")

    if not registros:
        print("[AVISO] Nenhuma mídia com GPS foi encontrada.")
        print(f"Total de mídias analisadas: {len(arquivos)}")
        print(f"Lista de mídias sem GPS salva em: {sem_gps_path}")
        return

    df = pd.DataFrame(registros)

    df = agrupar_por_gps(
        df=df,
        distancia_metros=distancia_metros,
        min_samples=min_samples
    )

    salvar_agrupamentos(
        df=df,
        pasta_saida=pasta_saida,
        mover=mover_arquivos
    )

    relatorio = pasta_saida / "relatorio_agrupamento_gps.csv"
    df.to_csv(relatorio, index=False)

    total_grupos_validos = df[df["grupo"] != -1]["grupo"].nunique()
    total_sem_grupo = int((df["grupo"] == -1).sum())

    print("Agrupamento concluído.")
    print("-" * 70)
    print(f"Total de mídias encontradas: {len(arquivos)}")
    print(f"Total de mídias com GPS: {len(df)}")
    print(f"Total de mídias sem GPS: {len(sem_gps)}")
    print(f"Total de regiões encontradas: {total_grupos_validos}")

    if total_sem_grupo > 0:
        print(f"Total de mídias classificadas como sem_grupo: {total_sem_grupo}")

    print(f"Relatório CSV salvo em: {relatorio}")

    if sem_gps:
        print(f"Lista de mídias sem GPS salva em: {sem_gps_path}")


if __name__ == "__main__":
    main()