set sc_base=C:\Users\MERFISH4\Code\storm-control\
call C:\Users\MERFISH4\Anaconda3\Scripts\activate.bat
call activate merfish4_env
cmd /k python %sc_base%\storm_control\hal4000\hal4000.py %sc_base%\storm_control\hal4000\xml\moffitt_merfish4_2cam_config.xml