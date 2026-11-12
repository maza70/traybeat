#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR=$(dirname "$SCRIPT_DIR") 

(

# Aufruf:
# ./svg-to-png.sh [GRÖSSE]

SOURCE_DIR="${ROOT_DIR}/src/traybeat/resources/svg"
OUTPUT_DIR="${ROOT_DIR}/src/traybeat/resources/png"
SIZE="24"

if ! command -v rsvg-convert >/dev/null 2>&1; then
    echo "Error: rsvg-convert is not installed."
    exit 1
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
    echo "error: source diectory not found: $SOURCE_DIR"
    exit 1
fi


mkdir -p "$OUTPUT_DIR"

count=0


while IFS= read -r -d '' svg; do
    filename="$(basename "$svg" .svg)"

    for variant in dark light; do
        if [[ "$variant" == "light" ]]; then
            color="#000000"
        else
            color="#ffffff"
        fi
        mkdir -p "$OUTPUT_DIR/${variant}"
        output="$OUTPUT_DIR/${variant}/${filename}.png"

        # currentColor ersetzen und SVG in PNG konvertieren
        sed "s/currentColor/${color}/g" "$svg" |
            rsvg-convert \
                --format=png \
                --width="$SIZE" \
                --height="$SIZE" \
                --output="$output"

        echo "Erzeugt: $output"
    done

    ((count+=1))
done < <(find "$SOURCE_DIR" -maxdepth 1 -type f -iname '*.svg' -print0)

echo
echo "finish: $count SVG-files converted."
)