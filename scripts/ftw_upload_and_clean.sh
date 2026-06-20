#!/bin/bash
# Upload improved FTW files to S3 and delete local copies
S3_DEST="s3://us-west-2.opendata.source.coop/tge-labs/ftw-global-data/predictions/vectors/alpha/fiboa"
DIR="$HOME/geodata/ftw/fiboa-improved"

for f in "$DIR"/ftw_global_*.parquet; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    echo "Uploading $name..."
    if aws s3 cp "$f" "$S3_DEST/$name"; then
        rm "$f"
        echo "  Uploaded and deleted $name"
    else
        echo "  FAILED to upload $name"
    fi
done
echo "Done. $(ls "$DIR"/ftw_global_*.parquet 2>/dev/null | wc -l) files remaining locally"
