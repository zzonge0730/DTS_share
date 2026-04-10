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
    class TCP_Server_Manager
    {
        TcpListener tcplistener;

        static List<TcpClient> tcpclients = new List<TcpClient>();

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
                string port = "50005";

                if (!isServerRunning)
                {
                    tcplistener = new TcpListener(IPAddress.Any, int.Parse(port));
                    tcplistener.Server.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
                    tcplistener.Start();

                    isServerRunning = true;
                }

                while (isServerRunning)
                {
                    Accept();
                }


            }

            catch (Exception ex)
            {
                Console.WriteLine(ex.Message);
            }

        }

        public void Accept()
        {
            try
            {
                TcpClient tcpclient = tcplistener.AcceptTcpClient();

                tcpclients.Add(tcpclient);

                Console.WriteLine("Client Connected");

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

                
                Console.WriteLine($"Send to Client : {message}");
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

                    Console.WriteLine($"Receive Message : {message}");
                }
            }
        }

        private void ReceiveCheck(string[] cmd)
        {
            try
            {

            }
            catch (Exception ex)
            {
                Console.WriteLine(ex.Message);
            }

        }
    }
}
