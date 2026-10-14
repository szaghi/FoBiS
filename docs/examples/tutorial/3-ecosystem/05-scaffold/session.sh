source ./env.sh
show status 'fobis ecosystem scaffold status'
quiet 'echo "# local edit" >> mathx/.github/workflows/ci.yml'
show drift 'fobis ecosystem scaffold status'
show project 'cd mathx && fobis scaffold status'
show sync 'cd mathx && fobis scaffold sync --yes && git status --short'
