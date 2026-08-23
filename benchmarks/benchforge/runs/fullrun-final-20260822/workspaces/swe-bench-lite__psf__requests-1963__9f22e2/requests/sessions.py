def resolve_redirects(self, req, resp, **kwargs):
    """Resolve and follow redirects.

    This method is called by :meth:`send` when a redirect response is
    received. It will follow the redirect if allowed, otherwise it will
    raise an exception.

    :param req: The original request
    :param resp: The response to check for redirects
    :param kwargs: Additional arguments to pass to :meth:`send`
    :return: The final response
    """
    # Get the Session configuration
    allow_redirects = kwargs.pop('allow_redirects', True)
    stream = kwargs.get('stream')
    timeout = kwargs.get('timeout')
    verify = kwargs.get('verify')
    cert = kwargs.get('cert')
    proxies = kwargs.get('proxies')
    
    # If redirects are not allowed, return the response as-is
    if not allow_redirects:
        return resp
    
    # Initialize the current request with the original request
    current_req = req
    
    # Follow redirects
    while resp.is_redirect:
        # Get the redirect URL
        url = resp.headers.get('location')
        
        # Handle relative redirects
        if url:
            # Resolve the redirect URL
            url = urlparse.urljoin(current_req.url, url)
        else:
            # No location header, can't redirect
            break
        
        # Check for too many redirects
        if len(resp.history) >= self.max_redirects:
            raise TooManyRedirects('Exceeded %s redirects.' % self.max_redirects)
        
        # Create a new request for the redirect
        # Use the current request (not original) to preserve method changes
        # from previous redirects (e.g., 303 changing POST to GET)
        redirect_req = current_req.copy()
        
        # Update the URL
        redirect_req.url = url
        
        # Handle method changes based on redirect status code
        if resp.status_code == codes.see_other:
            # 303 See Other: change method to GET
            redirect_req.method = 'GET'
            redirect_req.data = None
            redirect_req.json = None
        elif resp.status_code == codes.temporary_redirect:
            # 307 Temporary Redirect: preserve method
            pass
        elif resp.status_code == codes.permanent_redirect:
            # 308 Permanent Redirect: preserve method
            pass
        else:
            # Other redirects (301, 302): change method to GET for non-POST
            if current_req.method != 'HEAD':
                redirect_req.method = 'GET'
                redirect_req.data = None
                redirect_req.json = None
        
        # Update headers for redirect
        if 'Authorization' in redirect_req.headers:
            # Remove Authorization header for cross-domain redirects
            if urlparse.urlparse(url).netloc != urlparse.urlparse(current_req.url).netloc:
                del redirect_req.headers['Authorization']
        
        # Add to history
        resp.history.append(resp)
        
        # Prepare the redirect request
        redirect_req = self.prepare_request(redirect_req)
        
        # Send the redirect request
        resp = self.send(redirect_req, **kwargs)
        
        # Update current request for next iteration
        current_req = redirect_req
    
    return resp