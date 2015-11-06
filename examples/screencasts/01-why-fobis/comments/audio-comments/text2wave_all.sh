#!/bin/bash
for file in $( ls ../text-comments/*.txt ); do
  echo "Reading $file"
  bname=$(basename -s .txt $file)
  text2wave $file -o $bname'.wav'
done
