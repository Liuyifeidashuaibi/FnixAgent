const isPostmanCollection = (data) => {
  // Check standard format: data.info exists
  if (data && data.info) {
    return true;
  }
  
  // Check wrapped format: data.collection.info exists
  if (data && data.collection && data.collection.info) {
    return true;
  }
  
  return false;
};

module.exports = { isPostmanCollection };