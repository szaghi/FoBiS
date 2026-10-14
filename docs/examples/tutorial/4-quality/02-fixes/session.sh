show lint 'fobis lint --select COR002,COR040'
show diff 'fobis lint --select OBS005,OBS011,MDN021 --diff'
show baseline 'fobis lint --update-baseline && head -n 14 .fobis-lint-baseline.json'
show clean 'fobis lint'
