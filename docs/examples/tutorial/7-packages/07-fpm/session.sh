# a colleague's project is built with fpm: fobis add writes into its fpm.toml, and fpm does the rest
eval "${DOCS_FPM_SETUP:-}"
needs fpm
quiet 'cp -R "$DOCS_CHAPTER/report" ~/report'
show search 'fobis search --build fpm'
show add 'cd ~/report && fobis add strings'
show manifest 'cat ~/report/fpm.toml'
show fobis-only 'cd ~/report && fobis add lab:kinds'
show cmake-only 'cd ~/report && fobis add cmath'
quiet 'cd ~/report && fpm build'
quiet 'rm -f ~/report/build/cache.toml'
show run 'cd ~/report && fpm run 2>/dev/null'
show remove 'cd ~/report && fobis remove strings && cat fpm.toml'
