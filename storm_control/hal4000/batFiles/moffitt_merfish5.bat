set sc_base=C:\Users\MERFI\Code\storm-control\
call C:\ProgramData\Anaconda3\Scripts\activate.bat
call activate hal_env
cmd /k python %sc_base%\storm_control\hal4000\hal4000.py %sc_base%\storm_control\hal4000\xml\moffitt_merfish5_config.xml