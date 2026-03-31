#!/bin/bash
# download_model.sh
#
# Downloads a quantized GGUF model and uploads it to a Snowflake stage
# for use by the llama.cpp sidecar container in SPCS.
#
# Prerequisites:
#   - SnowCLI installed and configured
#   - wget or curl installed
#
# Usage:
#   ./download_model.sh <SNOW_CONNECTION> <DATABASE> <SCHEMA>

set -euo pipefail

SNOW_CONNECTION="${1:?Usage: ./download_model.sh <SNOW_CONNECTION> <DATABASE> <SCHEMA>}"
DATABASE="${2:?Usage: ./download_model.sh <SNOW_CONNECTION> <DATABASE> <SCHEMA>}"
SCHEMA="${3:?Usage: ./download_model.sh <SNOW_CONNECTION> <DATABASE> <SCHEMA>}"

MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_FILE="qwen2.5-1.5b-instruct-q4_k_m.gguf"
STAGE_NAME="LLM_MODELS"

echo "=== External Agent Model Setup ==="
echo "Connection: $SNOW_CONNECTION"
echo "Target:     $DATABASE.$SCHEMA"
echo "Model:      $MODEL_FILE"
echo ""

# Step 1: Download the model
if [ -f "$MODEL_FILE" ]; then
    echo "Model file already exists, skipping download."
else
    echo "Downloading model from HuggingFace..."
    wget -q --show-progress -O "$MODEL_FILE" "$MODEL_URL"
    echo "Download complete: $(ls -lh "$MODEL_FILE" | awk '{print $5}')"
fi

# Step 2: Create the stage in Snowflake
echo ""
echo "Creating stage $DATABASE.$SCHEMA.$STAGE_NAME..."
snow sql -c "$SNOW_CONNECTION" -q "
    USE DATABASE $DATABASE;
    USE SCHEMA $SCHEMA;
    CREATE STAGE IF NOT EXISTS $STAGE_NAME
        ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
"

# Step 3: Upload the model to the stage
echo ""
echo "Uploading model to stage (this may take a few minutes)..."
snow sql -c "$SNOW_CONNECTION" -q "
    PUT file://./$MODEL_FILE @$DATABASE.$SCHEMA.$STAGE_NAME
    AUTO_COMPRESS = FALSE
    OVERWRITE = TRUE;
"

echo ""
echo "=== Done ==="
echo "Model uploaded to: @$DATABASE.$SCHEMA.$STAGE_NAME/$MODEL_FILE"
echo ""
echo "You can verify with:"
echo "  snow sql -c $SNOW_CONNECTION -q \"LIST @$DATABASE.$SCHEMA.$STAGE_NAME;\""
