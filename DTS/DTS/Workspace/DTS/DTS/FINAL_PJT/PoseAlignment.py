import numpy as np

def order_points_and_optimize(poselist, start_idx):
    """
    3D 공간에서 최근접 이웃으로 순서를 정하고,
    2-Opt 알고리즘으로 경로를 최적화합니다.
    
    poselist: (N,7) with (x,y,z,qx,qy,qz,qw)
    returns: optimized ordered poses (N,7)
    """
    start_idx = start_idx[0]
    
    poses = np.array(poselist)
    pts3 = poses[:, :3]
    N = len(pts3)

    # 1. 최근접 이웃 알고리즘으로 초기 순서 결정 (3D 공간에서)
    visited = np.zeros(N, dtype=bool)
    ordered_idx = [start_idx]
    visited[start_idx] = True
    cur = start_idx

    for _ in range(N - 1):
        dists = np.linalg.norm(pts3 - pts3[cur], axis=1)
        dists[visited] = np.inf
        nxt = np.argmin(dists)
        
        ordered_idx.append(nxt)
        visited[nxt] = True
        cur = nxt

    # 2. 2-Opt 알고리즘으로 경로 최적화
    best_idx = list(ordered_idx)
    # improved = True
    # cnt = 0
    # while improved:
    #     improved = False
    #     cnt += 1
    #     print(cnt)
    #     # 경로의 시작과 끝점은 제외하고 순환합니다.
    #     for i in range(1, len(best_idx) - 2):
    #         for k in range(i + 1, len(best_idx) - 1):
    #             # i와 k를 기준으로 경로를 뒤집어 새로운 경로를 만듭니다.
    #             new_idx = list(best_idx)
    #             new_idx[i:k+1] = best_idx[i:k+1][::-1] 
                
    #             # 기존 경로와 새 경로의 '두 간선' 길이 비교
    #             # np.linalg.norm을 사용하여 3D 공간에서의 거리를 정확하게 계산
    #             dist_old = np.linalg.norm(pts3[best_idx[i-1]] - pts3[best_idx[i]]) + np.linalg.norm(pts3[best_idx[k]] - pts3[best_idx[k+1]])
    #             dist_new = np.linalg.norm(pts3[new_idx[i-1]] - pts3[new_idx[i]]) + np.linalg.norm(pts3[new_idx[k]] - pts3[new_idx[k+1]])
                
    #             if dist_new < dist_old:
    #                 best_idx = new_idx
    #                 improved = True
                    
    ordered_poses = poses[best_idx]
    return ordered_poses