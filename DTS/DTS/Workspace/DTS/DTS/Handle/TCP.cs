using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace DTS
{
    class TCP
    {
        TCP_Client_Manager visionclient;
        public TCP(TCP_Client_Manager vision, TCP_Client_Manager robot)
        {
            visionclient = vision;
            _ = robot;
        }
        public async void Handle_Robot(string message)
        {
            try
            {
                string[] cmd = message.Split(',');
                
                if (cmd[0] == "ready")
                {
                    await visionclient.SendMessageToServer(cmd[0]);
                }
                Console.WriteLine($"[Robot] Receive Message : {message}");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"ERROR : {ex}");
            }
        }

        public void Handle_Vision(string message)
        {
            try
            {
                Console.WriteLine($"[Vision] Receive Message : {message}");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"ERROR : {ex}");
            }
        }
    }
}
