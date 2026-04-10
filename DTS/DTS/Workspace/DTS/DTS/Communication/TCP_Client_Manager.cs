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
    class TCP_Client_Manager
    {
        public bool isClientConnected = false;

        TcpClient tcpclient;
        public TCP_Client_Manager()
        {

        }
        public async Task ConnectToServer(string ip, string port,string opponent)
        {
            if (!isClientConnected)
            {
                string serverip = ip;
                int serverport = int.Parse(port);

                try
                {
                    tcpclient = new TcpClient();

                    await tcpclient.ConnectAsync(ip, serverport);

                    Console.WriteLine($"Connect to Server : {serverip}:{port} Successfully");
                    isClientConnected = true;

                    NetworkStream stream = tcpclient.GetStream();

                    Task receivingTask = Task.Run(async () =>
                    {
                        await ReceiveDataFromServer(stream, tcpclient, serverport, opponent);
                    });
                    await Task.WhenAny(receivingTask);
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"Error While Connecting to Server: { ex.Message}");
                   
                }
            }
            else
            {
                Console.WriteLine($"Already Connected, but you try to connect again");
            }
        }
        public async Task ReceiveDataFromServer(NetworkStream stream, TcpClient client, int port, string opponent)
        {
            while (true)
            {
                try
                {
                    byte[] buffer = new byte[1024000];
                    int bytesRead = await stream.ReadAsync(buffer, 0, buffer.Length);

                    if (bytesRead == 0)
                    {
                        Console.WriteLine("Disconnected to Server.");
                        if (opponent == "vision" && Form1.form != null)
                        {
                            // Safety-first: empty vision stream is treated as protocol failure and latched in DTS.
                            Form1.form.Handle_Vision(string.Empty);
                        }
                        isClientConnected = false;
                        break;
                    }

                    string response = Encoding.ASCII.GetString(buffer, 0, bytesRead);

                    if (opponent == "robot") Form1.form.Handle_Robot(response);
                    else if (opponent == "vision") Form1.form.Handle_Vision(response);
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"Error While Reading Message From Server : {ex.Message}");

                    isClientConnected = false;
                    break;
                }
            }
        }

        public async Task SendMessageToServer(string message)
        {
            if (tcpclient.Connected)
            {
                NetworkStream stream = tcpclient.GetStream();
                byte[] data = Encoding.ASCII.GetBytes(message);
                await stream.WriteAsync(data, 0, data.Length);
                stream.Flush();
                Console.WriteLine($"Send To Vision : {message}");
            }
            else
            {
                Console.WriteLine("연결 없음"); ;
            }
        }

        public void Disconnect()
        {
            try
            {
                tcpclient?.Close();
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Disconnect ERROR: {ex.Message}");
            }
            finally
            {
                tcpclient = null;
                isClientConnected = false;
            }
        }
    }
}
