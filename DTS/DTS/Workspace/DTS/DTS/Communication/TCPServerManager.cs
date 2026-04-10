using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Net.Sockets;
using System.Net;
using System.IO;
using System.Threading;

namespace Robot_control
{
    class TCPServerManager
    {
        TcpListener tcplistener;

        static List<TcpClient> tcpclients = new List<TcpClient>();

        Logmanager logmanager = new Logmanager();

        Util util = new Util();

        public static double[] nj; 

        public static double[] nt;

        public static bool[] output = new bool[32];
        public static bool[] input = new bool[32];

        public bool isServerRunning = false;

        public void ServerThreadStart()
        {
            Thread serverthread = new Thread(new ThreadStart(StartServer));
            serverthread.Start();
        }
        public void StartServer()
        {
            try
            {
                string port = util.Loadconfig(8);

                if (!isServerRunning)
                {
                    tcplistener = new TcpListener(IPAddress.Any, int.Parse(port));
                    tcplistener.Server.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
                    tcplistener.Start();
                    util.InvokemessageLog(InfoLevel.INFO, "Start Server!");

                    isServerRunning = true;
                }

                while (isServerRunning)
                {
                    Accept();
                }
                

            }

            catch (Exception ex)
            {
                logmanager.WriteLog(LogLevel.ERROR, $"Connect ERROR :{ex.Message}");
                Console.WriteLine(ex.Message);
            }
            
        }

        public void Accept()
        {
            try
            {
                TcpClient tcpclient = tcplistener.AcceptTcpClient();

                tcpclients.Add(tcpclient);

                util.InvokemessageLog(InfoLevel.INFO, "Client Connected");

                ThreadPool.QueueUserWorkItem(_ => Receive(tcpclient));
                
            }

            catch (Exception ex)
            {
                Console.WriteLine($"Server Accept Error : {ex.Message}");
            }
        }

        public void Send(string message)
        {
            foreach (TcpClient c in tcpclients)
            {
                NetworkStream Stream = c.GetStream();

                byte[] buffer = Encoding.UTF8.GetBytes(message);
                Stream.Write(buffer, 0, buffer.Length);

                util.InvokemessageLog(InfoLevel.INFO, $"Send to client : {message}");
                logmanager.WriteLog(LogLevel.SEND, message);
            }
            
        }

        private Task Receive(TcpClient tcpclient)
        {
            tcpclient.Client.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);

            while (true)
            {
                if (tcpclient.Connected)
                {
                    NetworkStream stream = tcpclient.GetStream();
                    byte[] buffer = new byte[1024];
                    int bytes = stream.Read(buffer, 0, buffer.Length);
                    
                    if (bytes <= 0)
                    {
                        continue;
                    }

                    string message = Encoding.UTF8.GetString(buffer, 0, bytes);

                    ReceiveCheck(message.Split(','));

                    //util.InvokemessageLog(InfoLevel.INFO, $"Receive Message : {message}");
                    //logmanager.WriteLog(LogLevel.RECEIVE, message);
                }
            }
        }

        private void ReceiveCheck(string[] cmd)
        {
            try
            {
                nj = new double[6];
                nt = new double[6];

                //output = new bool[32];
                //input = new bool[32];


                int[] output_value = new int[4];
                int[] input_value = new int[4];

                if (cmd.Length > 10)
                {
                    for (int i = 0; i < 6; i++)
                    {
                        nj[i] = double.Parse(cmd[i]); // 
                        nt[i] = double.Parse(cmd[i + 6]);
                    }

                    for (int i = 12; i< 16; i++)
                    {
                        input_value[i-12] = int.Parse(cmd[i]);
                        output_value[i-12] = int.Parse(cmd[i + 4]);
                    }

                    string[] input_string;
                    input_string = new string[4];
                    char[] input_char;
                    input_char = new char[8];

                    string[] output_string;
                    output_string = new string[4];
                    char[] output_char;
                    output_char = new char[8];

                    for (int i = 0; i <4; i++)
                    {
                        input_string[i] = Convert.ToString(input_value[i], 2);
                        input_string[i] = input_string[i].PadLeft((8), '0');

                        output_string[i] = Convert.ToString(output_value[i], 2);
                        output_string[i] = output_string[i].PadLeft((8), '0');

                        //Console.WriteLine($"input_string[{i}]: " + input_string[i]);
                        //Console.WriteLine($"output_string[{i}]: " + output_string[i]);

                        input_char = input_string[i].ToCharArray();
                        Array.Reverse(input_char);

                        output_char = output_string[i].ToCharArray();
                        Array.Reverse(output_char);

                        for (int j = 0; j<8; j++)
                        {
                            

                            if (input_char[j].ToString() == "1")
                            {
                                input[j+ (i * 8)] = true;
                            }
                            else
                            {
                                input[j+ (i * 8)] = false;
                            }

                            //input[j] = bool.Parse(input_char[j].ToString());

                            if (output[j + (i * 8)])
                            {

                            }

                            if (output_char[j].ToString() == "1")
                            {
                                output[j + (i * 8)] = true;
                            }
                            else
                            {
                                output[j + (i * 8)] = false;
                            }

                            //input[j] = bool.Parse(input_char[j].ToString());

                            if (output[j + (i * 8)])
                            {

                            }

                            //Console.WriteLine($"output{j + (i * 8) + 1}: {output[j + (i * 8)]}");
                            //Console.WriteLine($"input{j+ (i * 8)+1}: {input[j+ (i * 8)]}");

                            //Console.WriteLine(input[j]);
                            //Console.WriteLine(output[j]);
                        }

                    }
                }

                for (int i = 0; i<cmd.Length; i++)
                {
                    //Console.WriteLine("data: " + cmd[i]);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine(ex.Message);
            }

        }
    }
}
