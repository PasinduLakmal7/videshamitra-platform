import React from 'react';

export const LoadingSpinner: React.FC<any> = (props) => {
  return <div className="loadingspinner">{props.children}</div>;
};
