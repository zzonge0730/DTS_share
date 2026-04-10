import string
def parser(a):
    status_code = a[0:4]
    Pose_num = int(a[6:9])
    V = list()
    A = list()
    MT = list()
    DO = list()
    for i in range(Pose_num):
        V.append(a[10 + 48 * Pose_num + 13 * i : 10 + 48 * Pose_num + 13 * i + 4])
        A.append(a[10 + 48 * Pose_num + 13 * i + 5])
        MT.append(a[10 + 48 * Pose_num + 13 * i + 7])
        DO.append(a[10 + 48 * Pose_num + 13 * i + 9 : 10 + 48 * Pose_num + 13 * i + 12])

    print(f'Status_code : {status_code}')
    print(f'Pose_num : {Pose_num}')
    print(f'V : {V}')
    print(f'A : {A}')
    print(f'MT : {MT}')
    print(f'DO : {DO}')


cnt = int(input("How many message do you have? : "))
for _ in range(cnt):
    message = str(input("Type the message : "))
    parser(message)