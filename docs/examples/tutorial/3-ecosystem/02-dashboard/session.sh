source ./env.sh
show dashboard 'fobis ecosystem dashboard --no-ci'
show json 'fobis ecosystem dashboard --no-ci --json | head -40'
show html 'fobis ecosystem dashboard --no-ci --format html --no-open -o dashboard.html && du -k dashboard.html'
