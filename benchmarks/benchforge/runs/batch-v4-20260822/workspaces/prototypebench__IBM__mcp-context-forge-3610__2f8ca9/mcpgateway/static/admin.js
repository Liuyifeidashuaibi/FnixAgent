function serverSideMemberSearch(query, callback) {
  // Perform server-side search for members
  $.getJSON('/admin/members/search/', { q: query }, function(data) {
    callback(data.results);
  });
}

function serverSideNonMemberSearch(query, callback) {
  // Perform server-side search for non-members
  $.getJSON('/admin/non-members/search/', { q: query }, function(data) {
    callback(data.results);
  });
}