using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Net;
using System.Net.Sockets;
using System.Windows.Forms;
using System.Threading;
using System.Drawing;
using System.IO;
using System.Numerics;


namespace Robot_control
{
    class TCPClientManager
    {
        NetworkStream networkstream;

        TcpClient robotclient;

        TcpClient visionclient;

        TcpClient tcpclient;

        TCPServerManager tcpservermanager;

        Util util;

        STLViewer stlviewer;

        Logmanager logmanager = new Logmanager();

        public static int? successcount = 0;

        public static int? othererror = 0;

        public static int? nopoint = 0;

        public static int? noresult = 0;

        public static int? planfailed = 0;

        string remessage = string.Empty;

        public string[] cmd;
        //
        bool stage1 = false;

        bool stage2 = false;

        bool stage3 = false;

        bool is_waiting = false;

        bool is_waitingrobot = false;

        bool is_waitingrobot_move = false;
        //
        public TCPClientManager()
        {
            stlviewer = new STLViewer();
        }

        public void ThreadStop(string opponent)
        {
            if (opponent == "robot" && robotclient != null)
            {
                robotclient.Close();
                robotclient = null;
            }

            if (opponent == "vision" && visionclient != null)
            {
                visionclient.Close();
                visionclient = null;
            }

            if (opponent == "opponent" && tcpclient != null)
            {
                tcpclient.Close();
                tcpclient = null;
            }
        }

        public async void Connect(string IP, string PORT, string opponent)
        {

            if (util == null)
            {
                util = new Util();
            }
            if (IP.Split('.').Length != 4 || PORT == "")
            {
                MessageBox.Show("IP or Port Wrong");
            }

            try
            {
                if (opponent == "Robot")
                {
                    if (robotclient == null)
                    {
                        robotclient = new TcpClient();
                    }
                    util.InvokemessageLog(InfoLevel.INFO, $"[{opponent}] try to connect...");
                    await robotclient.ConnectAsync(IPAddress.Parse(IP), int.Parse(PORT));

                    if (robotclient.Connected)
                    {
                        util.InvokemessageLog(InfoLevel.INFO, $"[{opponent}] Connected!");
                        Thread robotThread = new Thread(() => Receive(robotclient, opponent));
                        MainForm.form1.lb_robot.BackColor = Color.Green; //연결 상태 UI 표시

                        robotThread.Start(); //로봇 Receive 스레드 시작

                        _ = CheckConnect(robotclient, opponent);

                        logmanager.WriteLog(LogLevel.INFO, $"{opponent} CONNECT");
                    }
                }

                else if (opponent == "Vision")
                {
                    if (visionclient == null)
                    {
                        visionclient = new TcpClient();
                    }
                    util.InvokemessageLog(InfoLevel.INFO, $"[{opponent}] try to connect...");
                    await visionclient.ConnectAsync(IPAddress.Parse(IP), int.Parse(PORT));

                    if (visionclient.Connected)
                    {
                        util.InvokemessageLog(InfoLevel.INFO, $"[{opponent}] Connected!");
                        Thread visionThread = new Thread(() => Receive(visionclient, opponent));
                        MainForm.form1.lb_vision.BackColor = Color.Green; //연결 상태 UI 표시

                        visionThread.Start(); //비전 Receive 스레드 시작

                        _ = CheckConnect(visionclient, opponent);

                        logmanager.WriteLog(LogLevel.INFO, $"{opponent} CONNECT");
                    }
                }

                else if (opponent == "opponent")
                {
                    if (tcpclient == null)
                    {
                        tcpclient = new TcpClient();
                    }
                    util.InvokemessageLog(InfoLevel.INFO, $"[{opponent}] try to connect...");
                    await tcpclient.ConnectAsync(IPAddress.Parse(IP), int.Parse(PORT));

                    if (tcpclient.Connected)
                    {
                        util.InvokemessageLog(InfoLevel.INFO, $"[{opponent}] Connected!");
                        Thread tcpThread = new Thread(() => Receive(tcpclient, opponent));

                        tcpThread.Start();

                        _ = CheckConnect(tcpclient, opponent);

                        logmanager.WriteLog(LogLevel.INFO, $"{opponent} CONNECT");
                    }

                }
            }
            catch (Exception ex)
            {
                Console.WriteLine(ex.Message);
                logmanager.WriteLog(LogLevel.ERROR, $"ERROR : {ex.Message}");
                util.InvokemessageLog(InfoLevel.ERROR, $"[{opponent}] Connect ERROR");
            }

        }
        public void Send(TcpClient tcpclient, string message, string opponent)
        {
            if (util == null)
            {
                util = new Util();
            }
            try
            {
                NetworkStream networkstream = tcpclient.GetStream();
                byte[] buffer = Encoding.UTF8.GetBytes(message);
                networkstream.Write(buffer, 0, buffer.Length);

                util.InvokemessageLog(InfoLevel.INFO, $"Send to {opponent} : {message}");
                MainForm.form1.tb_message.Text = string.Empty;

                logmanager.WriteLog(LogLevel.SEND, message);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Send ERROR: {ex.Message}");
                logmanager.WriteLog(LogLevel.ERROR, ex.Message);
            }

        }

        public void RealSend(string opponent, string message)
        {
            if (opponent == "Robot")
            {
                Send(robotclient, message, opponent);
            }

            else if (opponent == "Vision")
            {
                Send(visionclient, message, opponent);
            }

            else if (opponent == "All")
            {
                Send(robotclient, message, "robot");
                Send(visionclient, message, "vision");
                Send(tcpclient, message, "opponent");
            }


        }

        public void Receive(TcpClient tcpclient, string opponent)
        {
            if (util == null)
            {
                util = new Util();
            }

            while (true)
            {
                if (tcpclient == null) { return; }

                if (tcpclient.Connected)
                {
                    try
                    {
                        networkstream = tcpclient.GetStream();
                        byte[] buffer = new byte[8096];
                        int bytes = networkstream.Read(buffer, 0, buffer.Length);
                        if (bytes <= 0)
                        {
                            continue;
                        }
                        remessage = Encoding.UTF8.GetString(buffer, 0, bytes);
                        cmd = remessage.Split(',');
                        if (opponent == "Vision")
                        {
                            ResultPose();
                        }

                        MainForm.form1.richTextBox1.Invoke(new MethodInvoker(delegate
                        {
                            if (opponent == "Robot")
                            {
                                MainForm.form1.richTextBox1.SelectionColor = Color.Blue;
                            }

                            else if (opponent == "Vision")
                            {
                                MainForm.form1.richTextBox1.SelectionColor = Color.Green;
                            }

                            else { MainForm.form1.richTextBox1.SelectionColor = Color.LightCoral; }

                        }));
                        util.InvokemessageLog(InfoLevel.INFO, $"[{opponent}] Receive message : {remessage}");

                        logmanager.WriteLog(LogLevel.RECEIVE, remessage);

                        Resultcheck();
                        MainForm.form1.InfoLoad();
                    }

                    catch (Exception ex)
                    {
                        Console.WriteLine($"Receive ERROR : {ex.Message}");
                        logmanager.WriteLog(LogLevel.ERROR, ex.Message);
                    }
                }

            }

        }

        public async Task CheckConnect(TcpClient tcpclient, string opponent)
        {
            while (true)
            {
                try
                {
                    if (!IsSockConnected(tcpclient))
                    {
                        util.InvokemessageLog(InfoLevel.INFO, $"[{opponent}] 연결이 끊어졌습니다.");
                        ThreadStop(opponent);

                        if (opponent == "Robot")
                        {
                            MainForm.form1.lb_robot.BackColor = Color.Red; // 연결상태 UI 표시
                        }
                        if (opponent == "Vision")
                        {
                            MainForm.form1.lb_vision.BackColor = Color.Red; // 연결상태 UI 표시
                        }
                        else { }

                        logmanager.WriteLog(LogLevel.INFO, "DISCONNECT");

                        // 연결이 끊어진 경우 루프를 종료
                        break;
                    }
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"CheckConnect Error: {ex.Message}");
                }

                await Task.Delay(1000); // 1초마다 연결 상태를 체크
            }
        }

        public bool IsSockConnected(TcpClient tcpclient)
        {
            try
            {
                return !(tcpclient.Client.Poll(1, SelectMode.SelectRead) && tcpclient.Client.Available == 0);

            }

            catch (SocketException ex)
            {
                return false;
            }

            catch (Exception ex)
            {
                return false;
            }

        }

        //public void WorkStart()
        //{
        //    try
        //    {
        //        startpoint = false;
        //        Send("P,5");
        //        Task.Run(() => Resultcheck());
        //    }

        //    catch (Exception ex)
        //    {
        //        Console.WriteLine($"ERROR : {ex.Message}");
        //    }


        //}


        //쿼터니언 값 말고 오일러 각으로 받아 해당 값 JPS 변환 및 이동
        //
        public void Resultcheck()
        {
            try
            {
                if (cmd != null)
                {

                    switch (cmd[0])
                    {
                        case "1":
                            is_waiting = false;

                            string x = cmd[1]; string y = cmd[2]; string z = cmd[3]; string r = cmd[4]; string p = cmd[5]; string Y = cmd[6];

                            string R = string.Empty;

                            x = x.PadRight((9), '0'); // 9자리 숫자를 맞추기 위해 오른쪽 끝에 '0' 추가
                            y = y.PadRight((9), '0');
                            z = z.PadRight((9), '0');
                            r = r.PadRight((9), '0');
                            p = p.PadRight((9), '0');
                            Y = Y.Replace("\r", "");
                            Y = Y.PadRight((10), '0');
                            R = util.Loadconfig(5);

                            RealSend("Robot", "S," + (x + "," + y + "," + z + "," + r + "," + p + "," + Y + "," + R));

                            is_waitingrobot = true;
                            _ = ResponseCheck("robot");
                       
                            MainForm.form1.ImageUpdate();

                            break;

                        case "Move_Start":
                            is_waitingrobot = false;
                            is_waitingrobot_move = true;

                            _ = ResponseCheck("robot_move");
                            util.StatusChange("robot_running");
                            
                            break;

                        case "2\r":
                            is_waiting = false;
                            othererror += 1;
                            util.InvokemessageLog(InfoLevel.ERROR, "Invalid command");
                            logmanager.WriteLog(LogLevel.ERROR, "Invalid command");
                            break;

                        case "3\r":
                            is_waiting = false;
                            othererror += 1;
                            util.InvokemessageLog(InfoLevel.ERROR, "Vision Project Not Loaded");
                            logmanager.WriteLog(LogLevel.ERROR, "Vision Project Not Loaded");
                            break;

                        case "4\r":
                            is_waiting = false;
                            nopoint += 1;
                            util.InvokemessageLog(InfoLevel.ERROR, "No Point Cloud");
                            logmanager.WriteLog(LogLevel.ERROR, "No Point Cloud");
                            break;

                        case "5\r":
                            is_waiting = false;
                            noresult += 1;
                            util.InvokemessageLog(InfoLevel.ERROR, "No Result");
                            logmanager.WriteLog(LogLevel.ERROR, "No Result");
                            break;

                        case "6\r":
                            is_waiting = false;
                            planfailed += 1;
                            util.InvokemessageLog(InfoLevel.ERROR, "Plan Failed");
                            logmanager.WriteLog(LogLevel.ERROR, "Plan Failed");
                            break;

                        case "7\r":
                            is_waiting = false;
                            othererror += 1;
                            util.InvokemessageLog(InfoLevel.ERROR, "Vision Other Error");
                            logmanager.WriteLog(LogLevel.ERROR, "Vision Other Error");
                            break;

                        case "finish":
                            is_waitingrobot_move = false;

                            successcount += 1;
                            util.StatusChange("success");
                            util.InvokemessageLog(InfoLevel.INFO, "1 Cycle Successfully Finish!");
                            logmanager.WriteLog(LogLevel.ERROR, "1 Cycle Successfully Finish!");

                            break;

                        case "Start":
                            RealSend("Vision", "trigger,3");

                            is_waiting = true;
                            _ = ResponseCheck("vision");

                            util.StatusChange("vision_running");
                            break;

                    }
                    util.WriteCount(successcount, othererror, nopoint, noresult, planfailed);
                }
            }

            catch (Exception ex)
            {
                Console.WriteLine(ex);
                stage1 = false; stage2 = false; stage3 = false;
            }

        }

        public void ConnectAll()
        {
            StreamReader reader = File.OpenText(DirectoryName.conifgfile);
            try
            {
                if (reader != null)
                {
                    if (tcpservermanager == null)
                    {
                        tcpservermanager = new TCPServerManager();
                    }

                    string[] config = reader.ReadToEnd().Split(',');
                    string robotip = config[0]; string robotport = config[1]; string visionip = config[2]; string visionport = config[3];
                    reader.Close();

                    Connect(robotip, robotport, "Robot"); //로봇 서버로 연결 시도
                    Connect(visionip, visionport, "Vision"); //비전 서버로 연결 시도

                    tcpservermanager.ServerThreadStart(); //서버 소켓 오픈

                }
            }

            catch (Exception ex)
            {
                logmanager.WriteLog(LogLevel.ERROR, ex.Message);
                Console.WriteLine(ex.Message);
            }

        }
        
        private async Task ResponseCheck(string opponent)
        {
            int ms = int.Parse(util.Loadconfig(6));
            int rms = int.Parse(util.Loadconfig(7));

            switch (opponent)
            {

                case "vision":
                    for (int i = 0; i <= 10; i++)
                    {
                        if (!is_waiting)
                        {
                            return;
                        }
                        await Task.Delay(ms / 10);
                    }
                    util.TimeOutMessage(opponent);
                    break;

                case "robot":
                    for (int i = 0; i <= 10; i++)
                    {
                        if (!is_waitingrobot)
                        {
                            return;
                        }
                        await Task.Delay(ms / 10);
                    }
                    util.TimeOutMessage(opponent);
                    break;

                case "robot_move":
                    for (int i = 0; i <= 10; i++)
                    {
                        if (!is_waitingrobot_move)
                        {
                            return;
                        }
                        await Task.Delay(rms / 10);
                    }
                    util.TimeOutMessage("robot");
                    break;

            }            
            
        }

        private void ResultPose()
        {
            if (cmd[0] == "Success1")
            {
                STLViewer.targetx = float.Parse(cmd[1]);
                STLViewer.targety = float.Parse(cmd[2]);
                STLViewer.targetz = float.Parse(cmd[3]);
                STLViewer.targetrx = float.Parse(cmd[4]);
                STLViewer.targetry = float.Parse(cmd[5]);
                STLViewer.targetrz = float.Parse(cmd[6]);
                STLViewer.resultmode = true;

                //stlviewer.FindPlyFile();
                STLViewer.isaddplymode = true;
                STLViewer.isnewplymode = true;

            }
            
        }

        private void QuattoEuler(string mx, string my, string mz, string x, string y, string z, string w)
        {
            // 쉽지 않다.

        }

        public void AllDisconnect()
        {
            ThreadStop("robot");
            ThreadStop("vision");
            ThreadStop("opponent");
        }
    }
}
