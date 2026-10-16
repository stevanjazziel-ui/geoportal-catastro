import unittest
import geopandas as gpd
from shapely.geometry import LineString, box
from review_police_verified_main_roads import candidates_from_shared_vertices


class RoadJunctionTests(unittest.TestCase):
    def frame(self, lines, names=None, kinds=None, bridges=None):
        n=len(lines)
        return gpd.GeoDataFrame({'osm_id':list(range(n)), 'name':names or ['Avenida Principal','Calle Lateral'][:n],
            'highway':kinds or ['primary','residential'][:n], 'bridge':bridges or [None]*n,
            'tunnel':[None]*n}, geometry=[LineString(p) for p in lines],crs=32717)

    def test_named_shared_vertex(self):
        roads=self.frame([[(-1,0),(0,0),(1,0)],[(0,0),(0,1)]])
        nodes=candidates_from_shared_vertices(roads,box(-5,-5,5,5))
        self.assertEqual(len(nodes),1)
        self.assertEqual(nodes[0]['degree'],3)
        self.assertEqual(nodes[0]['point'].wkt,'POINT (0 0)')

    def test_crossing_without_shared_vertex_is_not_junction(self):
        roads=self.frame([[(-1,0),(1,0)],[(0,-1),(0,1)]])
        self.assertEqual(candidates_from_shared_vertices(roads,box(-5,-5,5,5)),[])

    def test_local_streets_do_not_pass_as_principal(self):
        roads=self.frame([[(-1,0),(0,0),(1,0)],[(0,0),(0,1)]],kinds=['residential','residential'])
        self.assertEqual(candidates_from_shared_vertices(roads,box(-5,-5,5,5)),[])

    def test_explicit_local_catalog_does_not_relabel_local_as_principal(self):
        roads=self.frame([[(-1,0),(0,0),(1,0)],[(0,0),(0,1)]],kinds=['residential','residential'])
        nodes=candidates_from_shared_vertices(roads,box(-5,-5,5,5),require_principal=False)
        self.assertEqual(len(nodes),1)
        self.assertEqual(nodes[0]['principal'],[])
        self.assertEqual(nodes[0]['highways'],[])

    def test_unnamed_crossing_rejected(self):
        roads=self.frame([[(-1,0),(0,0),(1,0)],[(0,0),(0,1)]],names=['Avenida Principal',None])
        self.assertEqual(candidates_from_shared_vertices(roads,box(-5,-5,5,5)),[])

    def test_bridge_rejected(self):
        roads=self.frame([[(-1,0),(0,0),(1,0)],[(0,0),(0,1)]],bridges=['yes',None])
        self.assertEqual(candidates_from_shared_vertices(roads,box(-5,-5,5,5)),[])


if __name__=='__main__':
    unittest.main()
