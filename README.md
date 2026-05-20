# Agrupador de Mídias por GPS

Script em Python para organizar **imagens e vídeos** em pastas por proximidade geográfica, usando metadados GPS dos arquivos.

O script lê latitude/longitude com **ExifTool**, agrupa os pontos com **DBSCAN** usando distância Haversine e copia ou move os arquivos para pastas por região.

---

## Funcionalidades

- Lê GPS de imagens e vídeos.
- Suporta imagens: `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.webp`, `.heic`, `.heif`.
- Suporta vídeos: `.mp4`, `.mov`, `.avi`, `.mkv`, `.3gp`, `.m4v`.
- Agrupa mídias próximas por distância em metros.
- Gera relatório CSV com arquivo, tipo, coordenadas e grupo.
- Organiza mídias sem dado de GPS em uma pasta separada chamada `midias_sem_gps/`.
---

## Requisitos

- Python 3.10 ou superior
- ExifTool
- Bibliotecas Python:
  - pandas
  - numpy
  - scikit-learn
  - tqdm

---

## Instalação no Ubuntu/Linux

### 1. Instale o ExifTool

```bash
sudo apt update
sudo apt install libimage-exiftool-perl
```

Teste:

```bash
exiftool -ver
```

### 2. Crie e ative o ambiente virtual

```bash
python3 -m venv venv
source venv/bin/activate
```

Caso o `venv` não esteja instalado:

```bash
sudo apt install python3-venv python3-pip
```

### 3. Instale as dependências Python

```bash
pip install -r requirements.txt
```

---

## Instalação no Windows

### 1. Instale o Python

Instale Python 3.10 ou superior e marque a opção **Add Python to PATH**.

Teste no PowerShell:

```powershell
python --version
```

ou:

```powershell
py --version
```

### 2. Instale o ExifTool

Opção com Winget:

```powershell
winget install OliverBetz.ExifTool
```

Ou com Chocolatey:

```powershell
choco install exiftool
```

Depois feche e abra o PowerShell e teste:

```powershell
exiftool -ver
```

O comando `exiftool` precisa funcionar no terminal para o script executar corretamente.

### 3. Crie e ative o ambiente virtual

```powershell
python -m venv venv
.\venv\Scripts\activate
```

ou:

```powershell
py -m venv venv
.\venv\Scripts\activate
```

### 4. Instale as dependências

```powershell
pip install -r requirements.txt
```

---

## Como usar

### Linux/Ubuntu

```bash
python3 agrupar_midias_gps.py -i /caminho/para/midias -o midias_agrupadas -d 300
```

### Windows

```powershell
python agrupar_midias_gps.py -i "C:\caminho\para\midias" -o "midias_agrupadas" -d 300
```

---

## Parâmetros

| Parâmetro | Descrição |
|---|---|
| `-i`, `--input` | Pasta com as imagens e vídeos de entrada |
| `-o`, `--output` | Pasta onde os grupos serão salvos |
| `-d`, `--distancia` | Distância máxima, em metros, para agrupar mídias próximas |
| `--mover` | Move os arquivos em vez de copiar |
| `--min-samples` | Número mínimo de arquivos para formar grupo no DBSCAN |

Exemplo movendo arquivos:

```bash
python3 agrupar_midias_gps.py -i /caminho/para/midias -o completo -d 300 --mover
```

Atenção: `--mover` remove os arquivos da pasta original e transfere para a pasta de saída.

---

## Sugestões de distância

| Distância | Uso sugerido |
|---:|---|
| `100` m | Separação mais rigorosa |
| `300` m | Bom ponto inicial |
| `500` m | Regiões um pouco mais amplas |
| `1000` m | Bairros/localidades maiores |

---

## Saída esperada

Exemplo:

```text
completo/
├── regiao_000/
│   ├── IMG_001.jpg
│   └── VID_001.mp4
├── regiao_001/
│   └── IMG_010.jpg
├── midias_sem_gps/
│   ├── IMG_SEM_GPS.jpg
│   └── VIDEO_SEM_GPS.mp4
└── relatorio_agrupamento_gps.csv
```
O relatório `relatorio_agrupamento_gps.csv` contém:

```text
arquivo,nome_arquivo,extensao,tipo,latitude,longitude,grupo
```

---

## Verificar se um arquivo possui GPS

Linux:

```bash
exiftool -gps:all arquivo.jpg
exiftool -gps:all video.mp4
```

Windows:

```powershell
exiftool -gps:all "C:\Users\Carlos\Downloads\foto.jpg"
exiftool -gps:all "C:\Users\Carlos\Downloads\video.mp4"
```

Se não aparecer latitude/longitude, o arquivo provavelmente não possui GPS nos metadados.

---

## Observações

Nem toda foto ou vídeo possui GPS. A localização pode estar ausente quando:

- A localização do celular estava desativada.
- O app da câmera não tinha permissão de localização.
- A mídia veio de WhatsApp, Instagram, Telegram ou outro app que remove metadados.
- O arquivo foi editado/exportado por algum software.
- A câmera usada não possui GPS.

Em vídeos, o script considera uma única coordenada por arquivo, geralmente associada ao local de gravação ou início da gravação.

---

## Privacidade

Metadados GPS podem revelar locais sensíveis. Antes de compartilhar imagens, vídeos ou relatórios gerados, verifique se as coordenadas podem ser expostas publicamente.
