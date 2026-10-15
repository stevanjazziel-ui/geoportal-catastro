import unittest
import geopandas as gpd
from scipy.sparse.csgraph import connected_components
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union
from add_police_history_continuity import road_graph


class ContinuityTests(unittest.TestCase):
    def roads(self,coordinates,bridges=None):
        n=len(coordinates)
        return gpd.GeoDataFrame({'name':[f'Via {i}' for i in range(n)],'highway':['primary']*n,
            'bridge':bridges or [None]*n,'tunnel':[None]*n},geometry=[LineString(c) for c in coordinates],crs=32717)

    def test_geometric_crossing_does_not_connect(self):
        frame=self.roads([[(-10,0),(10,0)],[(0,-10),(0,10)]])
        nodes,edges,graph=road_graph(frame,box(-20,-20,20,20))
        count,_=connected_components(graph,directed=False)
        self.assertEqual(count,2)
        self.assertNotIn((0,0),nodes)

    def test_shared_vertex_connects(self):
        frame=self.roads([[(-10,0),(0,0),(10,0)],[(0,0),(0,10)]])
        _,_,graph=road_graph(frame,box(-20,-20,20,20))
        self.assertEqual(connected_components(graph,directed=False)[0],1)

    def test_endpoints_covered_but_gap_in_middle_not_connected(self):
        frame=self.roads([[(0,0),(200,0)]])
        disks=unary_union([Point(0,0).buffer(60),Point(200,0).buffer(60)])
        _,edges,graph=road_graph(frame,disks)
        self.assertEqual(graph.nnz,0)
        self.assertAlmostEqual(next(iter(edges.values()))['uncovered'],80)

    def test_overlapping_disks_cover_full_street(self):
        frame=self.roads([[(0,0),(300,0)]])
        disks=unary_union([Point(0,0).buffer(200),Point(300,0).buffer(200)])
        _,_,graph=road_graph(frame,disks)
        self.assertEqual(connected_components(graph,directed=False)[0],1)

    def test_bridge_not_used_for_unverified_ground_link(self):
        frame=self.roads([[(0,0),(20,0)]],bridges=['yes'])
        nodes,_,_=road_graph(frame,box(-20,-20,40,20))
        self.assertEqual(len(nodes),0)


if __name__=='__main__':
    unittest.main()
