# This file is part of the MapProxy project.
# Copyright (C) 2011 Omniscale <http://omniscale.de>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import random
import re
import time

import pytest

from mapproxy.cache.couchdb import CouchDBCache, CouchDBMDTemplate
from mapproxy.cache.tile import Tile
from mapproxy.grid.tile_grid import tile_grid
from mapproxy.test.image import create_tmp_image_buf
from mapproxy.test.unit.test_cache_tile import TileCacheTestBase


tile_image = create_tmp_image_buf((256, 256), color='blue')
tile_image2 = create_tmp_image_buf((256, 256), color='red')


@pytest.mark.skipif('MAPPROXY_TEST_COUCHDB' not in os.environ,
                    reason="MAPPROXY_TEST_COUCHDB not set")
class TestCouchDBCache(TileCacheTestBase):
    always_loads_metadata = True

    def setup_method(self):
        couch_address = os.environ['MAPPROXY_TEST_COUCHDB']
        db_name = 'mapproxy_test_%d' % random.randint(0, 100000)

        TileCacheTestBase.setup_method(self)

        md_template = CouchDBMDTemplate({
            'row': '{{y}}', 'tile_column': '{{x}}',
            'zoom': '{{level}}', 'time': '{{timestamp}}', 'coord': '{{wgs_tile_centroid}}'})
        self.cache = CouchDBCache(couch_address, db_name,
                                  file_ext='png', tile_grid=tile_grid(3857, name='global-webmarcator'),
                                  md_template=md_template)

    def teardown_method(self):
        import requests
        requests.delete(self.cache.couch_url)
        TileCacheTestBase.teardown_method(self)

    def test_default_coverage(self):
        assert self.cache.coverage is None

    def test_store_bulk_with_overwrite(self):
        tile = self.create_tile((0, 0, 4))
        self.create_cached_tile(tile)

        assert self.cache.is_cached(Tile((0, 0, 4)))
        loaded_tile = Tile((0, 0, 4))
        assert self.cache.load_tile(loaded_tile)
        assert loaded_tile.source_buffer().read() == tile.source_buffer().read()

        assert not self.cache.is_cached(Tile((1, 0, 4)))

        tiles = [self.create_another_tile((x, 0, 4)) for x in range(2)]
        assert self.cache.store_tiles(tiles)

        assert self.cache.is_cached(Tile((0, 0, 4)))
        loaded_tile = Tile((0, 0, 4))
        assert self.cache.load_tile(loaded_tile)
        # check that tile is overwritten
        assert loaded_tile.source_buffer().read() != tile.source_buffer().read()
        assert loaded_tile.source_buffer().read() == tiles[0].source_buffer().read()

    def test_double_remove(self):
        tile = self.create_tile()
        self.create_cached_tile(tile)
        assert self.cache.remove_tile(tile)
        assert self.cache.remove_tile(tile)


class TestCouchDBMDTemplate(object):
    def test_empty(self):
        template = CouchDBMDTemplate({})
        doc = template.doc(Tile((0, 0, 1)), tile_grid(4326))

        assert doc['timestamp'] == pytest.approx(time.time(), 0.1)

    def test_fixed_values(self):
        template = CouchDBMDTemplate({'hello': 'world', 'foo': 123})
        doc = template.doc(Tile((0, 0, 1)), tile_grid(4326))

        assert doc['timestamp'] == pytest.approx(time.time(), 0.1)
        assert doc['hello'] == 'world'
        assert doc['foo'] == 123

    def test_template_values(self):
        template = CouchDBMDTemplate({'row': '{{y}}', 'tile_column': '{{x}}',
                                      'zoom': '{{level}}', 'time': '{{timestamp}}', 'coord': '{{wgs_tile_centroid}}',
                                      'datetime': '{{utc_iso}}', 'coord_webmerc': '{{tile_centroid}}'})
        doc = template.doc(Tile((1, 0, 2)), tile_grid(3857))

        assert doc['time'] == pytest.approx(time.time(), 0.1)
        assert 'timestamp' not in doc
        assert doc['row'] == 0
        assert doc['tile_column'] == 1
        assert doc['zoom'] == 2
        assert doc['coord'][0] == pytest.approx(-45.0)
        assert doc['coord'][1] == pytest.approx(-79.17133464081945)
        assert doc['coord_webmerc'][0] == pytest.approx(-5009377.085697311)
        assert doc['coord_webmerc'][1] == pytest.approx(-15028131.25709193)
        assert re.match(r'20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ', doc['datetime']), doc['datetime']
