using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Net;
using System.Net.Sockets;
using System.Threading;

namespace DTS
{
    public delegate void LogDataDelegate(string data);

    public delegate void RecvDataDelegate(string data);
    class UDPSocket
    {
        public const string CRLF = "\r\n";

        private static bool udpConnection = false;
        private static bool isMsgReceive = false;
        private static bool isAsync = true;
        private static bool isMsgSend = false;
        public static LogDataDelegate evtLogData { get; set; }
        public static RecvDataDelegate evtRecvData { get; set; }

        private static UdpClient udp;

        private static Thread ReceiveThread;

        public static IPEndPoint TargetIPEndPoint;
        public static IPEndPoint MyIPEndPoint;
        public string IP { get; } = "127.0.0.1";
        //public string IP { get; } = "100.100.100.100";
        public int Port { get; } = 2500;

        public string TargetIP { get; } = "127.0.0.1";
        public int TargetPort { get; } = 2500;

        public static int Connect(string TargetIP, int TargetPort, string IP, int Port)
            {
            if (!udpConnection)
            {
                try
                {
                    IPAddress targetiPAddress = IPAddress.Parse(TargetIP);
                    TargetIPEndPoint = new IPEndPoint(targetiPAddress, TargetPort);

                    IPAddress myIPAddress = IPAddress.Parse(IP);
                    MyIPEndPoint = new IPEndPoint(myIPAddress, Port);
                    if (udp != null)
                    {
                        CloseProcess();
                    }

                    udp = new UdpClient(MyIPEndPoint);  // udpClient에 자기자신 IP , Port 설정

                    udp.Connect(TargetIPEndPoint);

                    Console.WriteLine($"Socket Open..{myIPAddress}:{Port}");

                    udpConnection = true;

                    ReceiveThread = new Thread(ReceiveData); // 연속적으로 데이터를 받기 위해 쓰레드 생성
                    ReceiveThread.IsBackground = true;
                    ReceiveThread.Start();

                    Console.WriteLine($"Waiting Receive Data..{targetiPAddress}:{TargetPort}");
                }
                catch (Exception)
                {
                    Console.WriteLine("Fail Connect UDP..");
                    udpConnection = false;
                }
            }
            else
            {
                Console.WriteLine("Already Connected to Robot, Please Disconnect and Retry");
            }
            return 0;

        }

        public static int CloseProcess() // 쓰레드와 UDPClient 종료
        {
            try
            {

                //udp = new UdpClient(MyIPEndPoint);
                udpConnection = false;
                udp?.Close();
                udp?.Dispose();
                udp = null;
                isMsgReceive = false;
                isMsgSend = false;
                TargetIPEndPoint = null;
                MyIPEndPoint = null;
                Console.WriteLine("Close UDP");
            }
            catch (Exception)
            {
                Console.WriteLine("Can not Close UDP: ");
            }
            return 0;
        }



        private static int SyncReceiveData()
        {
            var byteData = udp.Receive(ref TargetIPEndPoint); // data 동기 receive data
            var stringData = Encoding.ASCII.GetString(byteData); // byte[]에서 string으로 변환

            RecvData(stringData); // 다른 class에 알리기 위한 event 생성
            Console.WriteLine("ReceiveData from Robot : " + stringData + " IP-" + TargetIPEndPoint.Address.ToString() + " Port: " + TargetIPEndPoint.Port.ToString());

            return 0;
        }

        private static int ASyncReceiveData()
        {
            udp.BeginReceive(new AsyncCallback(AsyncReceiveCallback), udp);// data 비동기 receive data
            while (isMsgReceive)
            {
                Thread.Sleep(10);
            }
            isMsgReceive = false;
            return 0;
        }

        private static void AsyncReceiveCallback(IAsyncResult result)
        {
            if (result.IsCompleted)
            {
                var byteData = ((UdpClient)result.AsyncState).EndReceive(result, ref TargetIPEndPoint); // 버퍼에 있는 데이터 취득
                var stringData = Encoding.ASCII.GetString(byteData); // byte[]에서 string으로 변환

                Form1.form.Handle_Robot(stringData);

                isMsgReceive = true;

                

                RecvData(stringData); // 다른 class에 알리기 위한 event 생성
                Console.WriteLine("ReciveData : " + stringData + " IP-" + TargetIPEndPoint.Address.ToString() + " Port: " + TargetIPEndPoint.Port.ToString());

            }
        }

        public static void ReceiveData()
        {
            while (udpConnection)
            {
                if (udp == null)
                {
                    Thread.Sleep(10);
                    continue;
                }
                if (udp.Client.Available != 0 || udp.Available != 0) // 버퍼에 받은 데이터가 있는지 확인
                {
                    try
                    {
                        if (isAsync)
                            ASyncReceiveData();
                        else
                            SyncReceiveData();
                    }
                    catch (ObjectDisposedException)
                    {
                        return;
                    }
                    catch (Exception e)
                    {
                        Console.WriteLine("Recive Err : " + e.ToString());
                    }
                }
                else
                {
                    Thread.Sleep(10);
                }
            }
        }

        private static int SyncSendData(string data)
        {
            byte[] sendData = Encoding.ASCII.GetBytes(data); // string에서 byte[]로 변환
            udp.Send(sendData, sendData.Length); // 동기 Send data

            Console.WriteLine("Send Data : " + data + " IP-" + TargetIPEndPoint.Address.ToString() + " Port: " + TargetIPEndPoint.Port.ToString());

            return 0;
        }

        private static void ASyncSendCallback(IAsyncResult result)
        {
            isMsgSend = true;
        }

        private static int ASyncSendData(string data)
        {
            isMsgSend = false;

            if (udp == null || !udpConnection)
            {
                Console.WriteLine("Send Data Err : UDP not connected");
                return 0;
            }

            var sendData = Encoding.ASCII.GetBytes(data); // string에서 byte[]로 변환
            udp.BeginSend(sendData, sendData.Length, new AsyncCallback(ASyncSendCallback), udp); // 비동기 Send data
            while (!isMsgSend)
            {
                Thread.Sleep(10);
            }
         
            Console.WriteLine("Send Data : " + data + " IP-" + TargetIPEndPoint.Address.ToString() + " Port: " + TargetIPEndPoint.Port.ToString());


            return 0;
        }

        public static int SendData(string data)
        {
            try
            {
                if (string.IsNullOrWhiteSpace(data))
                {
                    Console.WriteLine("Send Data Err : empty payload");
                    return 0;
                }

                string trimmed = data.TrimStart();
                bool isRobotPosePayload = trimmed.StartsWith("1100,", StringComparison.Ordinal);
                if (isRobotPosePayload && !Form1.CanTransmitRobotPoses())
                {
                    string reason = Form1.GetRobotSendBlockReason();
                    Console.WriteLine($"[SendGuard] Blocked robot pose send. reason={reason}");
                    return 0;
                }

                if (udp == null || !udpConnection)
                {
                    Console.WriteLine("Send Data Err : UDP not connected");
                    return 0;
                }

                data += CRLF;

                if (isAsync)
                    ASyncSendData(data);
                else
                    SyncSendData(data);
            }
            catch (Exception ex)
            {
                Console.WriteLine("Send Data Err : " + ex.ToString());
            }

            return 0;
        }


        private static int RecvData(string str)
        {
            if (evtRecvData != null)
                evtRecvData(str);

            return 0;
        }        
    }
}
