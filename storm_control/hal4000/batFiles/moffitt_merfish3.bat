set sc_base=C:\Users\MERFISH3\Code\storm-control\
call C:\Users\MERFISH3\Anaconda3\Scripts\activate.bat
call activate merfish3_env
cmd /k python %sc_base%\storm_control\hal4000\hal4000.py %sc_base%\storm_control\hal4000\xml\moffitt_merfish3_config.xml