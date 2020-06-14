mkdir -p ./controlserver/log
[ -a ./controlserver/log/logview.txt ] || (> ./controlserver/log/logview.txt; ln -s ./controlserver/log/logview.txt ./controlserver/logview.txt)
mkdir -p ./httpserver/sessions
mkdir -p ./httpserver/public/tmp-scripts

xterm -e "cd $PWD/controlserver; python ./controlserver.py" &
sleep 10
xterm -e "cd $PWD/httpserver; python ./httpserver.py" &
