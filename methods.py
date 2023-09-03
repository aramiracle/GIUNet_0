import torch
import networkx as nx
import numpy as np
import scipy.linalg
import multiprocessing

# Convert edge_index to NetworkX graph
def edge_index_to_nx_graph(edge_index, num_nodes):
    edge_list = edge_index.t().tolist()
    G = nx.Graph()
    G.add_nodes_from(range(num_nodes))
    G.add_edges_from(edge_list)
    return G

#Calculatiing normalized Laplacian of graph
def normalized_laplacian(adjacency_matrix: torch.Tensor) -> torch.Tensor:
    """ Computes the symmetric normalized Laplacian matrix """
    num_nodes = adjacency_matrix.shape[0]
    d = torch.sum(adjacency_matrix, dim=1)
    Dinv_sqrt = torch.diag(1 / torch.sqrt(d))
    Ln = torch.eye(num_nodes, device=adjacency_matrix.device) - torch.mm(torch.mm(Dinv_sqrt, adjacency_matrix), Dinv_sqrt)
    Ln = 0.5 * (Ln + Ln.T)
    return Ln

#Approximataion of eigenvectors of matrix
def approximate_matrix(g, k):
    _, v = scipy.linalg.eigh(g, subset_by_index=[0, min(k - 1, g.shape[0] - 1)])
    return torch.tensor(np.single(v))

def calculate_centrality(graph, method, result_queue, index):
    centrality = method(graph)
    result_queue.put((index, centrality))

def extract_numerical_values(centrality_dict):
    # Extract numerical values from the centrality dictionary
    return [value for value in centrality_dict.values()]

def all_centralities(graph):
    centrality_methods = [
        (nx.algorithms.centrality.closeness_centrality, "closeness_centrality"),
        (nx.algorithms.centrality.degree_centrality, "degree_centrality"),
        (nx.algorithms.centrality.betweenness_centrality, "betweenness_centrality"),
        (nx.algorithms.centrality.load_centrality, "load_centrality"),
        (nx.algorithms.centrality.subgraph_centrality, "subgraph_centrality"),
        (nx.algorithms.centrality.harmonic_centrality, "harmonic_centrality")
    ]
    
    manager = multiprocessing.Manager()
    result_queue = manager.Queue()
    processes = []
    
    for index, (method, name) in enumerate(centrality_methods):
        process = multiprocessing.Process(target=calculate_centrality, args=(graph, method, result_queue, index))
        processes.append(process)
        process.start()
    
    for process in processes:
        process.join()
    
    centralities_dict = {}
    while not result_queue.empty():
        index, centrality = result_queue.get()
        method_name = centrality_methods[index][1]
        centralities_dict[method_name] = centrality
    
    # Extract numerical values and convert them to tensors with dtype=float
    centralities = [torch.tensor(extract_numerical_values(centralities_dict[method_name]), dtype=torch.float) for (_, method_name) in centrality_methods]
    
    return torch.stack(centralities, dim=1)

# Select top-k graph based on scores
def top_k_pool(scores, edge_index, h, ratio):
    num_nodes = h.shape[0]
    values, idx = torch.topk(scores.squeeze(), max(2, int(ratio * num_nodes)))  # Get top-k values and indices
    new_h = h[idx, :]  # Select top-k nodes
    values = torch.unsqueeze(values, -1)
    new_h = torch.mul(new_h, values)  # Apply weights to nodes
    g = adjacency_matrix(edge_index, num_nodes=num_nodes)  # Create adjacency matrix
    un_g = torch.matmul(g.bool().float(), torch.matmul(g.bool().float(), g.bool().float())).bool().float()  # Calculate unnormalized graph
    un_g = un_g[idx, :][:, idx]  # Select top-k subgraph
    g = norm_g(un_g)  # Normalize the graph
    return g, new_h, idx

# Create adjacency matrix from edge_index
def adjacency_matrix(edge_index, num_nodes=None):
    if num_nodes is None:
        num_nodes = edge_index.max().item() + 1
    adj_matrix = torch.zeros((num_nodes, num_nodes))
    adj_matrix[edge_index[0], edge_index[1]] = 1
    return adj_matrix

# Normalize the graph
def norm_g(g):
    return g / (g.sum(1, keepdim=True) + 1e-8)