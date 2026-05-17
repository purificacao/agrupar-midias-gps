from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from sklearn.cluster import DBSCAN
import argparse
import numpy as np
import pandas as pd
import shutil


# ==========================
# CONFIGURAÇÕES GERAIS
# ==========================

EXTENSOES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}


# ==========================
# ARGUMENTOS DE TERMINAL
# ==========================

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Agrupa fotos por proximidade geográfica usando metadados GPS "
            "presentes no EXIF das imagens."
        )
    )

    parser.add_argument(
        "-i", "--input",
        type=Path,
        required=True,
        help="Pasta onde estão as imagens de entrada."
    )

    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("fotos_agrupadas"),
        help="Pasta onde serão salvos os grupos. Padrão: fotos_agrupadas."
    )

    parser.add_argument(
        "-d", "--distancia",
        type=float,
        default=300,
        help="Distância máxima, em metros, para agrupar fotos próximas. Padrão: 300."
    )

    parser.add_argument(
        "--mover",
        action="store_true",
        help="Move os arquivos em vez de copiá-los."
    )

    return parser.parse_args()


# ==========================
# FUNÇÕES DE EXIF / GPS
# ==========================

def extrair_exif(imagem_path):
    """
    Extrai os metadados EXIF de uma imagem usando Pillow.
    """
    try:
        with Image.open(imagem_path) as img:
            exif_raw = img._getexif()

        if not exif_raw:
            return None

        exif = {}

        for tag_id, valor in exif_raw.items():
            tag = TAGS.get(tag_id, tag_id)

            if tag == "GPSInfo":
                gps_data = {}

                for gps_id, gps_valor in valor.items():
                    gps_tag = GPSTAGS.get(gps_id, gps_id)
                    gps_data[gps_tag] = gps_valor

                exif["GPSInfo"] = gps_data

            else:
                exif[tag] = valor

        return exif

    except Exception as e:
        print(f"[ERRO] Não foi possível ler EXIF de {imagem_path}: {e}")
        return None


def racional_para_float(valor):
    """
    Converte valores racionais do EXIF para float.

    O EXIF pode retornar valores como:
    - IFDRational
    - tupla, exemplo: (55, 1)
    - número comum
    """
    try:
        return float(valor)
    except TypeError:
        return valor[0] / valor[1]


def dms_para_decimal(dms, ref):
    """
    Converte coordenadas no formato graus, minutos e segundos para decimal.

    Exemplo:
    14° 47' 55.30'' Sul -> -14.798694
    """
    graus = racional_para_float(dms[0])
    minutos = racional_para_float(dms[1])
    segundos = racional_para_float(dms[2])

    decimal = graus + minutos / 60 + segundos / 3600

    ref = str(ref).upper()

    if ref in ["S", "W", "SUL", "OESTE"]:
        decimal *= -1

    return decimal


def extrair_gps(imagem_path):
    """
    Extrai latitude e longitude em graus decimais.
    Retorna None caso a imagem não tenha GPS.
    """
    exif = extrair_exif(imagem_path)

    if not exif or "GPSInfo" not in exif:
        return None

    gps = exif["GPSInfo"]

    try:
        lat = dms_para_decimal(
            gps["GPSLatitude"],
            gps["GPSLatitudeRef"]
        )

        lon = dms_para_decimal(
            gps["GPSLongitude"],
            gps["GPSLongitudeRef"]
        )

        return lat, lon

    except KeyError:
        return None


# ==========================
# FUNÇÕES DE ARQUIVOS
# ==========================

def listar_imagens(pasta):
    """
    Lista imagens dentro da pasta, incluindo subpastas.
    """
    return [
        p for p in pasta.rglob("*")
        if p.suffix.lower() in EXTENSOES and p.is_file()
    ]


def salvar_agrupamentos(df, pasta_saida, mover=False):
    """
    Copia ou move as imagens para pastas por grupo.
    """
    pasta_saida.mkdir(parents=True, exist_ok=True)

    for idx, row in df.iterrows():
        grupo = int(row["grupo"])
        origem = Path(row["arquivo"])

        pasta_grupo = pasta_saida / f"regiao_{grupo:03d}"
        pasta_grupo.mkdir(parents=True, exist_ok=True)

        destino = pasta_grupo / origem.name

        # Evita sobrescrever arquivos com mesmo nome
        if destino.exists():
            destino = pasta_grupo / f"{origem.stem}_{idx}{origem.suffix}"

        if mover:
            shutil.move(str(origem), str(destino))
        else:
            shutil.copy2(str(origem), str(destino))


# ==========================
# AGRUPAMENTO GEOGRÁFICO
# ==========================

def agrupar_por_gps(df, distancia_metros):
    """
    Agrupa coordenadas próximas usando DBSCAN com métrica haversine.

    O DBSCAN recebe coordenadas em radianos.
    O eps é a distância máxima entre pontos, convertida de metros para radianos.
    """
    raio_terra_m = 6_371_000

    coords = df[["latitude", "longitude"]].to_numpy()
    coords_rad = np.radians(coords)

    eps_rad = distancia_metros / raio_terra_m

    modelo = DBSCAN(
        eps=eps_rad,
        min_samples=1,
        metric="haversine"
    )

    labels = modelo.fit_predict(coords_rad)

    df = df.copy()
    df["grupo"] = labels

    return df


# ==========================
# FUNÇÃO PRINCIPAL
# ==========================

def main():
    args = parse_args()

    pasta_imagens = args.input
    pasta_saida = args.output
    distancia_metros = args.distancia
    mover_arquivos = args.mover

    if not pasta_imagens.exists():
        print(f"[ERRO] A pasta de entrada não existe: {pasta_imagens}")
        return

    if not pasta_imagens.is_dir():
        print(f"[ERRO] O caminho informado não é uma pasta: {pasta_imagens}")
        return

    print("Iniciando leitura das imagens...")
    print(f"Pasta de entrada: {pasta_imagens}")
    print(f"Pasta de saída: {pasta_saida}")
    print(f"Distância de agrupamento: {distancia_metros} metros")
    print(f"Modo: {'mover arquivos' if mover_arquivos else 'copiar arquivos'}")
    print("-" * 60)

    imagens = listar_imagens(pasta_imagens)

    if not imagens:
        print("[AVISO] Nenhuma imagem foi encontrada na pasta de entrada.")
        return

    registros = []
    sem_gps = []

    for img_path in imagens:
        gps = extrair_gps(img_path)

        if gps is None:
            sem_gps.append(str(img_path))
            continue

        lat, lon = gps

        registros.append({
            "arquivo": str(img_path),
            "nome_arquivo": img_path.name,
            "latitude": lat,
            "longitude": lon
        })

    if not registros:
        print("[AVISO] Nenhuma imagem com metadados GPS foi encontrada.")
        print(f"Total de imagens analisadas: {len(imagens)}")
        return

    df = pd.DataFrame(registros)

    df = agrupar_por_gps(df, distancia_metros)

    salvar_agrupamentos(
        df=df,
        pasta_saida=pasta_saida,
        mover=mover_arquivos
    )

    relatorio = pasta_saida / "relatorio_agrupamento_gps.csv"
    df.to_csv(relatorio, index=False)

    if sem_gps:
        sem_gps_path = pasta_saida / "imagens_sem_gps.txt"

        with open(sem_gps_path, "w", encoding="utf-8") as f:
            for item in sem_gps:
                f.write(item + "\n")

    print("Agrupamento concluído.")
    print("-" * 60)
    print(f"Total de imagens encontradas: {len(imagens)}")
    print(f"Total de imagens com GPS: {len(df)}")
    print(f"Total de imagens sem GPS: {len(sem_gps)}")
    print(f"Total de regiões encontradas: {df['grupo'].nunique()}")
    print(f"Relatório CSV salvo em: {relatorio}")

    if sem_gps:
        print(f"Lista de imagens sem GPS salva em: {sem_gps_path}")


if __name__ == "__main__":
    main()