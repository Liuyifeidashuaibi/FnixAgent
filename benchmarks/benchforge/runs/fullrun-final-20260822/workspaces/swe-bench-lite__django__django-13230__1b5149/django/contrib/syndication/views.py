from django.contrib.syndication.views import Feed

# Add comments argument to feed.add_item() method
# This enables item_comments to be defined directly without using item_extra_kwargs

class Feed(Feed):
    def add_item(self, title, description, link, comments=None, **kwargs):
        """
        Add an item to the feed with optional comments.
        
        The comments parameter is used for the item_comments feed item attribute.
        """
        item = {
            'title': title,
            'description': description,
            'link': link,
        }
        if comments is not None:
            item['comments'] = comments
        item.update(kwargs)
        self.items.append(item)
