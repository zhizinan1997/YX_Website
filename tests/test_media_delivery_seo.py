import unittest

from app.routes.media_delivery import public_asset_mimetype


class MediaDeliverySeoTests(unittest.TestCase):
    def test_public_image_mime_types_are_deterministic(self):
        self.assertEqual(public_asset_mimetype('product.webp'), 'image/webp')
        self.assertEqual(public_asset_mimetype('product.avif'), 'image/avif')
        self.assertEqual(public_asset_mimetype('product.jpg'), 'image/jpeg')
        self.assertEqual(public_asset_mimetype('product.png'), 'image/png')
        self.assertEqual(public_asset_mimetype('diagram.svg'), 'image/svg+xml')
